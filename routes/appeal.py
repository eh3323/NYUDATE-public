"""
Appeal system routes for NYU CLASS Professor Review System

This module contains routes for handling appeals and appeal success pages.
"""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from background_tasks import get_task_manager
from utils.decorators import rate_limit
from utils.email_sender import send_admin_notification

# This will be set by the main app
db = None
Submission = None
Appeal = None
AppealEvidence = None
verify_turnstile = None
send_email_async = None

# Create appeal blueprint
appeal_bp = Blueprint('appeal', __name__)

@appeal_bp.route("/appeal/<int:submission_id>", methods=["GET", "POST"])
@rate_limit(limit=10, window=300, per_route=True)  # 每5分钟最多10次申诉操作
def appeal(submission_id: int):
    sub = Submission.query.get_or_404(submission_id)
    if request.method == "GET":
        return render_template("appeal.html", sub=sub)
    
    # Turnstile check
    ts_token = request.form.get("cf-turnstile-response") or request.form.get("turnstile_token")
    if not verify_turnstile(ts_token, request.headers.get("CF-Connecting-IP") or request.remote_addr):
        flash("验证失败，请重试", "error")
        return render_template("appeal.html", sub=sub), 400
    
    # 基本表单验证
    email = (request.form.get("email") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    if not email or not reason:
        flash("请填写邮箱与申诉理由", "error")
        return render_template("appeal.html", sub=sub), 400
    
    # 创建申诉记录
    appeal_obj = Appeal(submission_id=submission_id, email=email, reason=reason)
    db.session.add(appeal_obj)
    db.session.flush()  # 获取ID用于关联证据
    
    # 处理 Google Drive 证据链接
    evidence_drive_link = (request.form.get("evidence_drive_link") or "").strip()
    evidence_description = (request.form.get("evidence_description") or "").strip()
    
    if evidence_drive_link:
        # 简单验证 Google Drive 链接格式
        if not evidence_drive_link.startswith(('https://drive.google.com/', 'https://docs.google.com/')):
            flash("请提供有效的 Google Drive 链接", "error")
            return render_template("appeal.html", sub=sub), 400
        
        # 创建申诉证据记录
        evidence = AppealEvidence(
            appeal_id=appeal_obj.id,
            category="google_drive",
            drive_link=evidence_drive_link,
            description=evidence_description or "Google Drive 证据材料"
        )
        db.session.add(evidence)
    
    db.session.commit()

    # 发送管理员申诉通知邮件
    try:
        subject_name = sub.get_display_name(masked=False) or "未知"
        notification_content = f"新的申诉提交\n\n申诉者：{email}\n原评价对象：{subject_name}\n申诉理由：{reason}\n提交时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n请登录管理后台查看详情。"
        send_admin_notification("新申诉待处理", notification_content)
    except Exception as e:
        current_app.logger.warning(f"发送申诉通知失败: {e}")

    # 提交后台任务：发送申诉相关邮件
    appeal_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    sender_addr = current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config.get("MAIL_USERNAME")
    task_manager = get_task_manager()
    
    # 给申诉人发送确认邮件
    if email:
        evidence_note = ""
        if evidence_drive_link:
            evidence_note = """
            <p><strong>重要提醒：</strong>请确保您提供的 Google Drive 链接设置为"任何人都可查看"权限，并包含以下材料：</p>
            <ul style="margin-left: 20px;">
                <li>证明您本人身份的材料（如学生证、身份证等）</li>
                <li>支持您申诉理由的相关证据</li>
            </ul>
            """
        
        user_email_data = {
            'subject': "NYU Dating Copilot - 申诉提交确认",
            'recipients': email,
            'email_title': "申诉已收到",
            'email_content': f"""
            <p>您的申诉已成功提交到 NYU Dating Copilot 系统。</p>
            
            <p>我们理解您对相关内容可能存在的担忧，我们的管理团队将认真审查您的申诉并在合理时间内给出处理结果。</p>
            
            {evidence_note}
            
            <p><strong>下一步：</strong>我们会仔细核实相关情况和您提供的证据材料。如果 Google Drive 链接无法访问或缺少必要的身份验证材料，我们会通过邮件联系您补充。处理完成后会第一时间邮件通知您。</p>
            """,
            'details': f"""
            <strong>相关记录ID：</strong>#{submission_id}<br>
            <strong>申诉时间：</strong>{appeal_time}<br>
            <strong>申诉ID：</strong>#{appeal_obj.id}
            """,
            'sender': sender_addr
        }
        
        task_manager.submit_task(
            f"email_appeal_user_{appeal_obj.id}",
            send_email_async,
            user_email_data,
            max_retries=3
        )
    
    # 给管理员发送通知邮件
    admin_rcpt = current_app.config.get("MAIL_USERNAME") or current_app.config.get("MAIL_DEFAULT_SENDER")
    if admin_rcpt:
        evidence_info = ""
        if evidence_drive_link:
            evidence_info = f"""
            <p><strong>证据材料：</strong>申诉人已提供 Google Drive 链接</p>
            <p style="margin-left: 20px; color: #666;"><strong>链接：</strong><a href="{evidence_drive_link}" target="_blank">{evidence_drive_link}</a></p>
            <p style="margin-left: 20px; color: #666;"><strong>说明：</strong>{evidence_description or '无'}</p>
            <p style="color: #d63384;"><strong>⚠️ 审核要点：</strong>请确认链接可访问且包含身份验证材料</p>
            """
        
        admin_email_data = {
            'subject': "NYU Dating Copilot - 新申诉通知",
            'recipients': admin_rcpt,
            'email_title': "收到新申诉",
            'email_content': f"""
            <p>系统收到一条新的申诉，请及时处理。</p>
            
            <p><strong>申诉摘要：</strong></p>
            <p>{reason[:300]}{'...' if len(reason) > 300 else ''}</p>
            
            {evidence_info}
            """,
            'details': f"""
            <strong>记录ID：</strong>#{submission_id}<br>
            <strong>申诉人邮箱：</strong>{email}<br>
            <strong>申诉时间：</strong>{appeal_time}<br>
            <strong>申诉ID：</strong>#{appeal_obj.id}
            """,
            'button_text': "查看申诉详情",
            'button_url': f"{request.host_url}admin/appeals" if hasattr(request, 'host_url') else None,
            'sender': sender_addr
        }
        
        task_manager.submit_task(
            f"email_appeal_admin_{appeal_obj.id}",
            send_email_async,
            admin_email_data,
            max_retries=3
        )

    flash("申诉已提交，我们会尽快处理。", "success")
    return redirect(url_for("appeal.appeal_success", appeal_id=appeal_obj.id))


@appeal_bp.route("/appeal/success/<int:appeal_id>")
def appeal_success(appeal_id: int):
    appeal = Appeal.query.get_or_404(appeal_id)
    return render_template("appeal_success.html", appeal=appeal)


def init_appeal_routes(database_instance, models, functions):
    """Initialize appeal routes with required dependencies"""
    global db, Submission, Appeal, AppealEvidence, verify_turnstile, send_email_async
    
    db = database_instance
    Submission = models['Submission']
    Appeal = models['Appeal']
    AppealEvidence = models['AppealEvidence']
    verify_turnstile = functions['verify_turnstile']
    send_email_async = functions['send_email_async']
    
    return appeal_bp