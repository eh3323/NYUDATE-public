"""
Submission management routes for NYU CLASS Professor Review System

This module contains routes for submission upload and success pages.
"""

import os
import secrets
import mimetypes
import magic
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from werkzeug.utils import secure_filename
from background_tasks import get_task_manager
from utils.decorators import rate_limit
from utils.security import sanitize_html, validate_file_security
from utils.email_sender import send_admin_notification

# This will be set by the main app
db = None
ReviewStatus = None
Submission = None
Evidence = None
moderate_content = None
verify_turnstile = None
generate_thumbnails_async = None
send_email_async = None

# Create submission blueprint
submission_bp = Blueprint('submission', __name__)

@submission_bp.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return render_template("upload.html")

    # Check if this is a moderation-only request
    action = request.form.get('action')
    if action == 'moderate':
        # Only perform content moderation and return JSON result
        description = (request.form.get("description") or "").strip()
        if not description:
            return jsonify({
                'action': 'FLAG_AND_FIX',
                'reasons': ['Empty description'],
                'client_notice': '请填写文字描述'
            }), 400
        
        # Sanitize description to prevent XSS
        description = sanitize_html(description)
        
        # Perform content moderation
        moderation_result = moderate_content(description)
        return jsonify(moderation_result)

    # Check if moderation was already passed (skip redundant moderation)
    moderation_passed = request.form.get('moderation_passed') == 'true'

    # Get form data first
    form_data = {
        'submitter_email': (request.form.get("submitter_email") or "").strip(),
        'professor_cn_name': (request.form.get("professor_cn_name") or "").strip(),
        'professor_en_name': (request.form.get("professor_en_name") or "").strip(),
        'professor_unique_identifier': (request.form.get("professor_unique_identifier") or "").strip(),
        'professor_birthday': (request.form.get("professor_birthday") or "").strip(),
        'description': (request.form.get("description") or "").strip(),
        'tag_positive': bool(request.form.get("tag_positive")),
        'tag_calm': bool(request.form.get("tag_calm")),
        'tag_leadership': bool(request.form.get("tag_leadership")),
        'tag_homework_heavy': bool(request.form.get("tag_homework_heavy")),
        'tag_loyal': bool(request.form.get("tag_loyal")),
        'tag_stable': bool(request.form.get("tag_stable")),
        'tag_sincere': bool(request.form.get("tag_sincere")),
        'tag_humorous': bool(request.form.get("tag_humorous")),
        'tag_custom': (request.form.get("tag_custom") or "").strip(),
        'allow_public_evidence': bool(request.form.get("allow_public_evidence")),
        'privacy_homepage': bool(request.form.get("privacy_homepage")),
    }

    # Turnstile check
    ts_token = request.form.get("cf-turnstile-response") or request.form.get("turnstile_token")
    if not verify_turnstile(ts_token, request.headers.get("CF-Connecting-IP") or request.remote_addr):
        flash("验证失败，请重试", "error")
        return render_template("upload.html", form_data=form_data), 400

    submitter_email = form_data['submitter_email']
    professor_cn_name = form_data['professor_cn_name'] or None
    professor_en_name = form_data['professor_en_name'] or None
    professor_unique_identifier = form_data['professor_unique_identifier'] or None
    professor_birthday = form_data['professor_birthday'] or None

    if not submitter_email:
        flash("必须填写邮箱", "error")
        return render_template("upload.html", form_data=form_data), 400

    if not (professor_cn_name or professor_en_name):
        flash("必须至少填写TA中文名或英文名之一", "error")
        return render_template("upload.html", form_data=form_data), 400

    description = form_data['description']
    if not description:
        flash("请填写文字描述", "error")
        return render_template("upload.html", form_data=form_data), 400
    
    # Sanitize description to prevent XSS
    description = sanitize_html(description)
    
    # 内容审核 - 如果前端已经通过审核则跳过
    if not moderation_passed:
        moderation_result = moderate_content(description)
        
        # 如果审核未通过，返回修改建议
        if moderation_result.get('action') == 'FLAG_AND_FIX':
            # 将审核结果存储在form_data中，以便模板使用
            form_data['moderation_result'] = moderation_result
            
            # 显示审核失败消息
            client_notice = moderation_result.get('client_notice', '内容需要修改后才能发布')
            flash(client_notice, "warning")
            
            return render_template("upload.html", form_data=form_data), 400

    tag_positive = form_data['tag_positive']
    tag_calm = form_data['tag_calm']
    tag_leadership = form_data['tag_leadership']
    tag_homework_heavy = form_data['tag_homework_heavy']
    tag_loyal = form_data['tag_loyal']
    tag_stable = form_data['tag_stable']
    tag_sincere = form_data['tag_sincere']
    tag_humorous = form_data['tag_humorous']
    tag_custom = form_data['tag_custom'] or None

    # 强制所有用户开放缩略图展示
    allow_public_evidence = True
    privacy_homepage = form_data['privacy_homepage']

    submission = Submission(
        submitter_email=submitter_email,
        professor_cn_name=professor_cn_name,
        professor_en_name=professor_en_name,
        professor_unique_identifier=professor_unique_identifier,
        professor_birthday=professor_birthday,
        tag_positive=tag_positive,
        tag_calm=tag_calm,
        tag_leadership=tag_leadership,
        tag_homework_heavy=tag_homework_heavy,
        tag_loyal=tag_loyal,
        tag_stable=tag_stable,
        tag_sincere=tag_sincere,
        tag_humorous=tag_humorous,
        tag_custom=tag_custom,
        description=description,
        allow_public_evidence=allow_public_evidence,
        privacy_homepage=privacy_homepage,
        status=ReviewStatus.PENDING,
    )

    db.session.add(submission)
    db.session.flush()  # obtain id before saving files

    saved_files = []

    # Get evidence descriptions
    image_descriptions = request.form.getlist("image_descriptions")
    doc_descriptions = request.form.getlist("doc_descriptions")  
    chat_descriptions = request.form.getlist("chat_descriptions")

    # Images - 检查数量和总大小限制
    image_files = request.files.getlist("image_evidences")
    if len(image_files) > current_app.config['MAX_IMAGES_PER_SUBMISSION']:
        flash(f"图片数量超过限制，最多只能上传{current_app.config['MAX_IMAGES_PER_SUBMISSION']}张图片", "error")
        return redirect(url_for("submission.upload"))
    
    # 检查图片总大小
    images_total_size = sum(file.content_length or 0 for file in image_files if file and file.filename)
    if images_total_size > current_app.config['MAX_IMAGES_TOTAL_SIZE']:
        max_size_mb = current_app.config['MAX_IMAGES_TOTAL_SIZE'] / (1024 * 1024)
        current_size_mb = images_total_size / (1024 * 1024)
        flash(f"图片总大小超过限制，最大允许{max_size_mb:.0f}MB，当前{current_size_mb:.1f}MB", "error")
        return redirect(url_for("submission.upload"))
    
    for i, file in enumerate(image_files):
        if not file or not file.filename:
            continue
        
        # Enhanced security validation
        is_valid, error_msg = validate_file_security(file, 'image')
        if not is_valid:
            flash(f"图片文件安全检查失败: {error_msg}", "error")
            continue
            
        filename = secure_filename(file.filename)
        unique_name = f"s{submission.id}_img_{secrets.token_hex(8)}_{filename}"
        file_path = os.path.join(current_app.config["IMAGE_UPLOAD_DIR"], unique_name)
        file.save(file_path)
        try:
            mime_type = magic.from_file(file_path, mime=True)
        except Exception:
            mime_type = mimetypes.guess_type(file_path)[0] or None
        file_size = os.path.getsize(file_path)
        
        # Get description for this file
        description = image_descriptions[i] if i < len(image_descriptions) else ""
        
        # Create evidence record (缩略图将异步生成)
        evidence = Evidence(
            submission_id=submission.id,
            category="image",
            file_path=file_path,
            original_filename=filename,
            mime_type=mime_type,
            file_size=file_size,
            description=description,
        )
        saved_files.append(evidence)
        db.session.add(evidence)
        db.session.flush()  # Get the evidence ID

    # Documents - 检查数量和总大小限制
    doc_files = request.files.getlist("doc_evidences")
    if len(doc_files) > current_app.config['MAX_DOCS_PER_SUBMISSION']:
        flash(f"文档数量超过限制，最多只能上传{current_app.config['MAX_DOCS_PER_SUBMISSION']}个文档", "error")
        return redirect(url_for("submission.upload"))
    
    # 检查文档总大小
    total_size = sum(file.content_length or 0 for file in doc_files if file and file.filename)
    if total_size > current_app.config['MAX_DOCS_TOTAL_SIZE']:
        max_size_mb = current_app.config['MAX_DOCS_TOTAL_SIZE'] / (1024 * 1024)
        current_size_mb = total_size / (1024 * 1024)
        flash(f"文档总大小超过限制，最大允许{max_size_mb:.0f}MB，当前{current_size_mb:.1f}MB", "error")
        return redirect(url_for("submission.upload"))
    
    for i, file in enumerate(doc_files):
        if not file or not file.filename:
            continue
        
        # Enhanced security validation
        is_valid, error_msg = validate_file_security(file, 'doc')
        if not is_valid:
            flash(f"文档文件安全检查失败: {error_msg}", "error")
            continue
            
        filename = secure_filename(file.filename)
        unique_name = f"s{submission.id}_doc_{secrets.token_hex(8)}_{filename}"
        file_path = os.path.join(current_app.config["DOC_UPLOAD_DIR"], unique_name)
        file.save(file_path)
        try:
            mime_type = magic.from_file(file_path, mime=True)
        except Exception:
            mime_type = mimetypes.guess_type(file_path)[0] or None
        file_size = os.path.getsize(file_path)
        
        # Get description for this file
        description = doc_descriptions[i] if i < len(doc_descriptions) else ""
        
        # Create evidence record (占位符将异步生成)
        evidence = Evidence(
            submission_id=submission.id,
            category="document",
            file_path=file_path,
            original_filename=filename,
            mime_type=mime_type,
            file_size=file_size,
            description=description,
        )
        saved_files.append(evidence)
        db.session.add(evidence)
        db.session.flush()  # Get the evidence ID

    # Chat: 推荐录屏，照片也接受（视频或图片） - 检查数量和总大小限制
    chat_files = request.files.getlist("chat_recordings")
    if len(chat_files) > current_app.config['MAX_VIDEOS_PER_SUBMISSION']:
        flash(f"视频数量超过限制，最多只能上传{current_app.config['MAX_VIDEOS_PER_SUBMISSION']}个视频", "error")
        return redirect(url_for("submission.upload"))
    
    # 检查视频总大小
    videos_total_size = sum(file.content_length or 0 for file in chat_files if file and file.filename)
    if videos_total_size > current_app.config['MAX_VIDEOS_TOTAL_SIZE']:
        max_size_mb = current_app.config['MAX_VIDEOS_TOTAL_SIZE'] / (1024 * 1024)
        current_size_mb = videos_total_size / (1024 * 1024)
        flash(f"视频总大小超过限制，最大允许{max_size_mb:.0f}MB，当前{current_size_mb:.1f}MB", "error")
        return redirect(url_for("submission.upload"))
    
    for i, file in enumerate(chat_files):
        if not file or not file.filename:
            continue
        filename = secure_filename(file.filename)
        ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
        
        # Determine file type and validate security - 只接受视频文件
        if ext in current_app.config["ALLOWED_VIDEO_EXTENSIONS"]:
            is_valid, error_msg = validate_file_security(file, 'video')
            if not is_valid:
                flash(f"视频文件安全检查失败: {error_msg}", "error")
                continue
            unique_name = f"s{submission.id}_video_{secrets.token_hex(8)}_{filename}"
            file_path = os.path.join(current_app.config["VIDEO_UPLOAD_DIR"], unique_name)
            category = "video"
        else:
            flash(f"视频文件格式不支持: {file.filename}", "error")
            continue
            
        file.save(file_path)
        try:
            mime_type = magic.from_file(file_path, mime=True)
        except Exception:
            mime_type = mimetypes.guess_type(file_path)[0] or None
        file_size = os.path.getsize(file_path)
        
        # Get description for this file
        description = chat_descriptions[i] if i < len(chat_descriptions) else ""
        
        # Create evidence record (缩略图/占位符将异步生成)
        evidence = Evidence(
            submission_id=submission.id,
            category=category,
            file_path=file_path,
            original_filename=filename,
            mime_type=mime_type,
            file_size=file_size,
            description=description,
        )
        saved_files.append(evidence)
        db.session.add(evidence)
        db.session.flush()  # Get the evidence ID

    # 证据文件现在为可选，不再强制要求上传

    # Evidence records were already added during file processing
    db.session.commit()

    # 发送管理员通知邮件
    try:
        subject_name = professor_cn_name or professor_en_name or "未知"
        notification_content = f"新的评价提交等待审核\n\n提交者：{submitter_email}\n评价对象：{subject_name}\n提交时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n请登录管理后台查看详情。"
        send_admin_notification("新提交待审核", notification_content)
    except Exception as e:
        current_app.logger.warning(f"发送提交通知失败: {e}")

    # 提交后台任务：生成缩略图
    task_manager = get_task_manager(current_app._get_current_object())
    task_manager.submit_task(
        f"thumbnails_{submission.id}",
        generate_thumbnails_async,
        submission.id,
        max_retries=2
    )

    # 提交后台任务：发送邮件确认
    if submitter_email:
        professor_name = professor_cn_name or professor_en_name or professor_unique_identifier
        submit_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        
        email_data = {
            'subject': "NYU Dating Copilot - 评价提交确认",
            'recipients': submitter_email,
            'email_title': "提交成功！",
            'email_content': f"""
            <p>感谢您向 NYU Dating Copilot 提交评价！您的提交已成功收到并进入审核流程。</p>
            
            <p><strong>审核状态：</strong>等待处理</p>
            <p><strong>预计处理时间：</strong>30分钟内</p>
            
            <p>我们的审核团队将仔细查看您提交的内容，确保符合社区规范后发布。审核完成后会第一时间通过邮件通知您结果。</p>
            """,
            'details': f"""
            <strong>TA的姓名：</strong>{professor_name}<br>
            <strong>提交时间：</strong>{submit_time}<br>
            <strong>提交ID：</strong>#{submission.id}
            """
            # 移除了 button_text 和 button_url 参数
        }
        
        task_manager.submit_task(
            f"email_upload_{submission.id}",
            send_email_async,
            email_data,
            max_retries=3
        )

    flash("提交成功，已进入审核，预计30分钟内处理。", "success")
    return redirect(url_for("submission.upload_success", submission_id=submission.id))

@submission_bp.route("/success/<int:submission_id>")
@rate_limit(limit=20, window=300, per_route=True)  # 每5分钟最多20次访问上传成功页
def upload_success(submission_id: int):
    submission = Submission.query.get_or_404(submission_id)
    return render_template("success.html", submission=submission)

def init_submission_routes(database_instance, models, functions):
    """Initialize submission routes with required dependencies"""
    global db, ReviewStatus, Submission, Evidence, moderate_content, verify_turnstile
    global generate_thumbnails_async, send_email_async
    
    db = database_instance
    ReviewStatus = models['ReviewStatus']
    Submission = models['Submission']
    Evidence = models['Evidence']
    moderate_content = functions['moderate_content']
    verify_turnstile = functions['verify_turnstile']
    generate_thumbnails_async = functions['generate_thumbnails_async']
    send_email_async = functions['send_email_async']
    
    return submission_bp