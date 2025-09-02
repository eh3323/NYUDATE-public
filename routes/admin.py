"""
Admin routes for NYU CLASS Professor Review System

This module contains all admin routes including authentication, 
submission management, appeal management, and bulk operations.
"""

import os
import json
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from werkzeug.security import check_password_hash
from sqlalchemy import or_
from utils.decorators import rate_limit, admin_required
from utils.security import sanitize_html
from utils.email_sender import send_html_email

# This will be set by the main app
db = None
ReviewStatus = None
Submission = None
Appeal = None
csrf = None

# Create admin blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route("/login", methods=["GET", "POST"])
@rate_limit(limit=5, window=60)  # 5 per minute
def admin_login():
    if request.method == "GET":
        return render_template("admin/login.html")
    
    # Input validation
    password = request.form.get("password", "").strip()
    if not password:
        flash("请输入密码", "error")
        return render_template("admin/login.html"), 401
    
    # Check password using hash verification
    if check_password_hash(current_app.config["ADMIN_PASSWORD"], password):
        session["is_admin"] = True
        session.permanent = True
        next_page = request.args.get("next")
        return redirect(next_page or url_for("admin.admin_dashboard"))
    flash("密码错误", "error")
    return render_template("admin/login.html"), 401


@admin_bp.route("/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("main.index"))


@admin_bp.route("/")
@admin_required
def admin_dashboard():
    status = request.args.get("status")
    q = Submission.query
    if status in {ReviewStatus.PENDING, ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.HIDDEN}:
        q = q.filter(Submission.status == status)
    keyword = (request.args.get("q") or "").strip()
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            or_(
                Submission.professor_cn_name.ilike(like),
                Submission.professor_en_name.ilike(like),
                Submission.professor_unique_identifier.ilike(like),
                Submission.submitter_email.ilike(like),
                Submission.description.ilike(like),
            )
        )
    submissions = q.order_by(Submission.created_at.desc()).limit(200).all()
    
    # 获取待处理申诉数量
    pending_appeals_count = Appeal.query.filter(Appeal.status == "pending").count()
    
    return render_template("admin/dashboard.html", submissions=submissions, ReviewStatus=ReviewStatus, pending_appeals_count=pending_appeals_count)


@admin_bp.route("/submission/<int:submission_id>")
@admin_required
def admin_submission_detail(submission_id: int):
    sub = Submission.query.get_or_404(submission_id)
    return render_template("admin/submission_detail.html", sub=sub, ReviewStatus=ReviewStatus)


@admin_bp.route("/submission/<int:submission_id>/action", methods=["POST"])
@admin_required
def admin_submission_action(submission_id: int):
    sub = Submission.query.get_or_404(submission_id)
    action = request.form.get("action")
    note = (request.form.get("note") or "").strip() or None

    if action == "approve":
        sub.status = ReviewStatus.APPROVED
        current_app.logger.info(f"Admin action: approved submission {submission_id}")
    elif action == "reject":
        sub.status = ReviewStatus.REJECTED
        current_app.logger.info(f"Admin action: rejected submission {submission_id}")
    elif action == "hide":
        sub.status = ReviewStatus.HIDDEN
        current_app.logger.info(f"Admin action: hidden submission {submission_id}")
    elif action == "delete":
        db.session.delete(sub)
        db.session.commit()
        flash("已删除", "success")
        return redirect(url_for("admin.admin_dashboard"))
    elif action == "flag_toggle":
        sub.flagged = not sub.flagged
    elif action == "update":
        # admin can modify any field
        sub.professor_cn_name = (request.form.get("professor_cn_name") or "").strip() or None
        sub.professor_en_name = (request.form.get("professor_en_name") or "").strip() or None
        sub.professor_unique_identifier = (request.form.get("professor_unique_identifier") or "").strip() or None
        sub.professor_birthday = (request.form.get("professor_birthday") or "").strip() or None
        sub.description = sanitize_html((request.form.get("description") or "").strip())
        sub.tag_positive = bool(request.form.get("tag_positive"))
        sub.tag_calm = bool(request.form.get("tag_calm"))
        sub.tag_leadership = bool(request.form.get("tag_leadership"))
        sub.tag_homework_heavy = bool(request.form.get("tag_homework_heavy"))
        sub.tag_loyal = bool(request.form.get("tag_loyal"))
        sub.tag_stable = bool(request.form.get("tag_stable"))
        sub.tag_sincere = bool(request.form.get("tag_sincere"))
        sub.tag_humorous = bool(request.form.get("tag_humorous"))
        sub.tag_custom = (request.form.get("tag_custom") or "").strip() or None
        sub.allow_public_evidence = bool(request.form.get("allow_public_evidence"))
        sub.privacy_homepage = bool(request.form.get("privacy_homepage"))
        
        # 管理员可以修改点赞数
        try:
            new_like_count = int(request.form.get("like_count", sub.like_count))
            if new_like_count >= 0:
                sub.like_count = new_like_count
        except (ValueError, TypeError):
            pass  # 忽略无效输入
    else:
        flash("未知操作", "error")
        return redirect(url_for("admin.admin_submission_detail", submission_id=submission_id))

    if note is not None:
        sub.admin_notes = note
    
    # 先提交数据库更改，确保状态保存
    try:
        db.session.commit()
        current_app.logger.info(f"Database committed for submission {submission_id}, status: {sub.status}")
        
        # 重新查询以验证状态确实已更新
        sub_verified = Submission.query.get(submission_id)
        if sub_verified:
            if action == "approve" and sub_verified.status != ReviewStatus.APPROVED:
                current_app.logger.error(f"Status verification failed for submission {submission_id}: expected {ReviewStatus.APPROVED}, got {sub_verified.status}")
                flash("状态更新可能失败，请检查数据库", "error")
            elif action == "reject" and sub_verified.status != ReviewStatus.REJECTED:
                current_app.logger.error(f"Status verification failed for submission {submission_id}: expected {ReviewStatus.REJECTED}, got {sub_verified.status}")
                flash("状态更新可能失败，请检查数据库", "error")
            elif action == "hide" and sub_verified.status != ReviewStatus.HIDDEN:
                current_app.logger.error(f"Status verification failed for submission {submission_id}: expected {ReviewStatus.HIDDEN}, got {sub_verified.status}")
                flash("状态更新可能失败，请检查数据库", "error")
            # 使用验证后的对象进行后续操作
            sub = sub_verified
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Database commit failed for submission {submission_id}: {e}")
        flash("数据库操作失败", "error")
        return redirect(url_for("admin.admin_submission_detail", submission_id=submission_id))

    # 邮件：审核通过通知（在try-catch中，不影响数据库状态）
    if action == "approve" and sub.submitter_email and sub.status == ReviewStatus.APPROVED:
        try:
            professor_name = sub.professor_cn_name or sub.professor_en_name or sub.professor_unique_identifier
            approve_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
            
            email_content = f"""
            <p>🎉 恭喜！您提交的评价已通过审核并成功发布。</p>
            
            <p>感谢您为 NYU Dating Copilot 社区贡献真实、有价值的内容。您的分享将帮助其他同学做出更明智的选择。</p>
            
            <p><strong>现在其他用户可以：</strong></p>
            <ul>
                <li>在首页搜索中找到这条评价</li>
                <li>查看您分享的详细体验和标签</li>
                <li>参考您的经历做出决策</li>
            </ul>
            
            <p>如果后续需要更新或修改内容，请联系管理员。</p>
            """
            
            details = f"""
            <strong>TA的姓名：</strong>{professor_name}<br>
            <strong>审核通过时间：</strong>{approve_time}<br>
            <strong>记录ID：</strong>#{sub.id}
            """
            
            # 生成邮件专用的访问链接
            from utils.security import generate_email_access_token
            email_token = generate_email_access_token(sub.id, sub.submitter_email)
            email_link = f"{request.host_url}email/s/{sub.id}/{email_token}" if hasattr(request, 'host_url') else None
            
            send_html_email(
                subject="NYU Dating Copilot - 审核通过通知",
                recipients=sub.submitter_email,
                email_title="审核通过！",
                email_content=email_content,
                details=details,
                button_text="查看已发布内容",
                button_url=email_link
            )
            current_app.logger.info(f"审核通过邮件发送成功: submission {sub.id}")
        except Exception as e:
            current_app.logger.error(f"发送审核通过邮件失败 submission {sub.id}: {e}")
            # 不影响审核状态，只记录错误
    
    flash("操作成功", "success")
    return redirect(url_for("admin.admin_submission_detail", submission_id=submission_id))


@admin_bp.route("/appeals")
@admin_required
def admin_appeals():
    status = request.args.get("status")
    q = Appeal.query
    if status in {"pending", "resolved", "rejected"}:
        q = q.filter(Appeal.status == status)
    appeals = q.order_by(Appeal.created_at.desc()).limit(200).all()
    return render_template("admin/appeals.html", appeals=appeals)


@admin_bp.route("/appeal/<int:appeal_id>/action", methods=["POST"])
@admin_required
def admin_appeal_action(appeal_id: int):
    ap = Appeal.query.get_or_404(appeal_id)
    action = request.form.get("action")
    note = (request.form.get("note") or "").strip() or None

    if action == "resolve":
        ap.status = "resolved"
    elif action == "reject":
        ap.status = "rejected"
    elif action == "delete":
        db.session.delete(ap)
        db.session.commit()
        flash("申诉已删除", "success")
        return redirect(url_for("admin.admin_appeals"))
    else:
        flash("未知操作", "error")
        return redirect(url_for("admin.admin_appeals"))

    if note is not None:
        ap.admin_notes = note
    db.session.commit()
    
    # 发送申诉处理结果邮件通知
    if action in ["resolve", "reject"] and ap.email:
        process_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        submission = ap.submission
        professor_name = submission.professor_cn_name or submission.professor_en_name or submission.professor_unique_identifier
        
        if action == "resolve":
            # 申诉被同意
            email_content = f"""
            <p>您的申诉已经过仔细审核，我们决定<strong>同意</strong>您的申诉。</p>
            
            <p>感谢您提供的信息和证据，这有助于我们更好地维护社区内容的准确性和公正性。</p>
            
            <p><strong>处理结果：</strong></p>
            <ul>
                <li>申诉状态已更新为"已解决"</li>
                <li>相关记录将根据您的申诉进行相应调整</li>
                <li>如有必要，相关内容已被修改或移除</li>
            </ul>
            
            <p>如果您对处理结果有任何疑问，欢迎随时联系我们。</p>
            """
            
            email_title = "申诉已同意"
            
        else:  # action == "reject"
            # 申诉被拒绝
            email_content = f"""
            <p>您的申诉已经过仔细审核，经过综合考虑，我们决定<strong>维持原有内容</strong>。</p>
            
            <p>我们理解您的关切，但经过审查后认为相关内容符合我们的社区规范和准确性标准。</p>
            
            <p><strong>审核过程：</strong></p>
            <ul>
                <li>我们仔细审查了您提供的申诉理由和证据</li>
                <li>对相关内容进行了全面评估</li>
                <li>综合考虑了各方面信息后做出决定</li>
            </ul>
            
            <p>如果您有新的证据或信息，欢迎重新提交申诉。我们始终致力于维护公平、准确的内容环境。</p>
            """
            
            email_title = "申诉处理结果通知"
        
        # 申诉详情
        details = f"""
        <strong>申诉ID：</strong>#{ap.id}<br>
        <strong>相关记录：</strong>{professor_name}<br>
        <strong>处理时间：</strong>{process_time}<br>
        <strong>处理状态：</strong>{'已同意' if action == 'resolve' else '已拒绝'}
        """
        
        # 管理员备注
        if note:
            details += f"<br><strong>管理员备注：</strong>{note}"
        
        send_html_email(
            subject=f"NYU Dating Copilot - {email_title}",
            recipients=ap.email,
            email_title=email_title,
            email_content=email_content,
            details=details,
            button_text="查看相关记录",
            button_url=f"{request.host_url}s/{submission.id}" if hasattr(request, 'host_url') else None
        )
    
    flash("操作成功", "success")
    return redirect(url_for("admin.admin_appeals"))


@admin_bp.route("/bulk-action", methods=["POST"])
@admin_required
def admin_bulk_action():
    """处理批量操作：批量通过、拒绝、删除提交"""
    try:
        current_app.logger.info(f"Bulk action request: content_type={request.content_type}, is_json={request.is_json}")
        
        # 检查请求类型
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
            # 如果是表单数据，需要解析submission_ids
            if 'submission_ids' in data:
                data['submission_ids'] = json.loads(data['submission_ids'])
        
        current_app.logger.info(f"Bulk action data: {data}")
        
        if not data:
            current_app.logger.error("No data received in bulk action request")
            return jsonify({"success": False, "message": "无效的请求数据"}), 400
        
        action = data.get("action")
        submission_ids = data.get("submission_ids", [])
        
        if not action or not submission_ids:
            return jsonify({"success": False, "message": "缺少必要参数"}), 400
        
        if action not in ["approve", "reject", "delete"]:
            return jsonify({"success": False, "message": "无效的操作类型"}), 400
        
        # 验证提交ID
        submissions = Submission.query.filter(Submission.id.in_(submission_ids)).all()
        if len(submissions) != len(submission_ids):
            return jsonify({"success": False, "message": "部分提交不存在"}), 400
        
        processed_count = 0
        
        # 执行批量操作
        for submission in submissions:
            try:
                if action == "approve":
                    submission.status = ReviewStatus.APPROVED
                elif action == "reject":
                    submission.status = ReviewStatus.REJECTED
                elif action == "delete":
                    # 删除相关的证据文件
                    evidences_to_delete = list(submission.evidences)  # 创建副本避免迭代时修改
                    for evidence in evidences_to_delete:
                        try:
                            # 删除文件系统中的文件
                            if evidence.file_path and os.path.exists(evidence.file_path):
                                os.remove(evidence.file_path)
                            if evidence.thumbnail_path and os.path.exists(evidence.thumbnail_path):
                                os.remove(evidence.thumbnail_path)
                        except Exception as e:
                            current_app.logger.warning(f"删除文件失败: {e}")
                        
                        # 从数据库删除证据记录
                        db.session.delete(evidence)
                    
                    # 删除提交记录
                    db.session.delete(submission)
                
                processed_count += 1
                
            except Exception as e:
                current_app.logger.error(f"处理提交 {submission.id} 失败: {e}")
                continue
        
        # 提交数据库更改
        db.session.commit()
        
        # 验证批量操作是否成功
        if action in ["approve", "reject"]:
            expected_status = ReviewStatus.APPROVED if action == "approve" else ReviewStatus.REJECTED
            for submission_id in submission_ids:
                verified_sub = Submission.query.get(submission_id)
                if verified_sub and verified_sub.status != expected_status:
                    current_app.logger.error(f"批量操作验证失败: 提交 {submission_id} 期望状态 {expected_status}, 实际状态 {verified_sub.status}")
                else:
                    current_app.logger.info(f"批量操作验证成功: 提交 {submission_id} 状态为 {verified_sub.status if verified_sub else 'NOT_FOUND'}")
        
        # 记录操作日志
        action_text = {"approve": "批量通过", "reject": "批量拒绝", "delete": "批量删除"}[action]
        current_app.logger.info(f"管理员执行{action_text}操作，处理了 {processed_count} 个提交，ID: {submission_ids}")
        
        return jsonify({
            "success": True, 
            "processed_count": processed_count,
            "message": f"成功处理 {processed_count} 个项目"
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"批量操作失败: {e}")
        return jsonify({"success": False, "message": f"操作失败: {str(e)}"}), 500


@admin_bp.route("/seed")
@admin_required
def admin_seed():
    # create a few demo submissions without evidences
    now = datetime.utcnow()
    samples = [
        Submission(
            submitter_email="seed1@nyu.edu",
            professor_cn_name="张三",
            professor_en_name="John Zhang",
            professor_unique_identifier="jz1234",
            description="讲课清晰，作业适中，课堂互动较多。",
            tag_positive=True,
            tag_calm=True,
            allow_public_evidence=False,
            privacy_homepage=True,
            status=ReviewStatus.APPROVED,
            created_at=now,
            updated_at=now,
        ),
        Submission(
            submitter_email="seed2@nyu.edu",
            professor_cn_name="李四",
            professor_en_name="Alice Lee",
            professor_unique_identifier="al2345",
            description="作业偏多，但给分透明，助教响应快。",
            tag_homework_heavy=True,
            tag_leadership=True,
            allow_public_evidence=True,
            privacy_homepage=True,
            status=ReviewStatus.APPROVED,
            created_at=now,
            updated_at=now,
        ),
        Submission(
            submitter_email="seed3@nyu.edu",
            professor_en_name="Bob Smith",
            professor_unique_identifier="bs3456",
            description="课堂节奏偏慢，适合打好基础。",
            tag_calm=True,
            allow_public_evidence=False,
            privacy_homepage=False,
            status=ReviewStatus.APPROVED,
            created_at=now,
            updated_at=now,
        ),
    ]
    db.session.add_all(samples)
    db.session.commit()
    flash("已生成测试数据", "success")
    return redirect(url_for("admin.admin_dashboard"))


def init_admin_routes(database_instance=None, models=None, csrf_instance=None):
    """Initialize admin routes with required dependencies"""
    global db, ReviewStatus, Submission, Appeal, csrf
    
    if database_instance:
        db = database_instance
    if models:
        ReviewStatus = models['ReviewStatus']
        Submission = models['Submission']
        Appeal = models['Appeal']
    if csrf_instance:
        csrf = csrf_instance
        # Exempt bulk-action from CSRF protection
        csrf.exempt(admin_bulk_action)
    
    return admin_bp