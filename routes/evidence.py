"""
Evidence handling routes for NYU CLASS Professor Review System

This module contains routes for viewing evidence files and thumbnails.
"""

import os
from flask import Blueprint, send_from_directory, current_app, abort
from utils.decorators import admin_required, rate_limit
from utils.file_handler import generate_privacy_thumbnail

# This will be set by the main app
db = None
ReviewStatus = None
Evidence = None
AppealEvidence = None
generate_document_placeholder = None

# Create evidence blueprint
evidence_bp = Blueprint('evidence', __name__)

@evidence_bp.route("/evidence/<int:submission_id>/<int:evidence_id>")
@rate_limit(limit=30, window=300, per_route=True)  # 每5分钟最多30次证据访问
def get_evidence(submission_id: int, evidence_id: int):
    ev = Evidence.query.filter_by(id=evidence_id, submission_id=submission_id).first_or_404()
    sub = ev.submission
    if sub.status != ReviewStatus.APPROVED:
        abort(404)
    # 所有用户现在都强制开放缩略图展示，不再检查 allow_public_evidence
    
    # Always serve privacy-protected thumbnail instead of original file for public
    if ev.thumbnail_path and os.path.exists(ev.thumbnail_path):
        # Validate thumbnail path to prevent path traversal
        safe_path = os.path.abspath(ev.thumbnail_path)
        upload_base = os.path.abspath(current_app.config["BASE_UPLOAD_DIR"])
        
        # Ensure file is within upload directory
        if not safe_path.startswith(upload_base):
            current_app.logger.error(f"Thumbnail path outside upload directory: {ev.thumbnail_path}")
            abort(404, "File not found")
        
        directory, filename = os.path.dirname(safe_path), os.path.basename(safe_path)
        current_app.logger.info(f"Serving thumbnail: {directory}/{filename}")
        return send_from_directory(directory, filename, as_attachment=False)
    else:
        # If no thumbnail exists, try to generate one on-demand
        current_app.logger.info(f"Generating on-demand thumbnail for evidence {ev.id}, category: {ev.category}")
        try:
            if ev.category == "image" and ev.file_path and os.path.exists(ev.file_path):
                thumbnail_path = generate_privacy_thumbnail(ev.file_path, ev.id)
                if thumbnail_path:
                    ev.thumbnail_path = thumbnail_path
                    db.session.commit()
                    directory, filename = os.path.dirname(thumbnail_path), os.path.basename(thumbnail_path)
                    current_app.logger.info(f"Generated image thumbnail: {directory}/{filename}")
                    return send_from_directory(directory, filename, as_attachment=False)
            elif ev.category in ["document", "video", "chat_video"]:
                placeholder_path = generate_document_placeholder(ev.id, ev.original_filename, ev.description)
                if placeholder_path:
                    ev.thumbnail_path = placeholder_path
                    db.session.commit()
                    directory, filename = os.path.dirname(placeholder_path), os.path.basename(placeholder_path)
                    current_app.logger.info(f"Generated document placeholder: {directory}/{filename}")
                    return send_from_directory(directory, filename, as_attachment=False)
            elif ev.category == "chat_image" and ev.file_path and os.path.exists(ev.file_path):
                thumbnail_path = generate_privacy_thumbnail(ev.file_path, ev.id)
                if thumbnail_path:
                    ev.thumbnail_path = thumbnail_path
                    db.session.commit()
                    directory, filename = os.path.dirname(thumbnail_path), os.path.basename(thumbnail_path)
                    current_app.logger.info(f"Generated chat image thumbnail: {directory}/{filename}")
                    return send_from_directory(directory, filename, as_attachment=False)
        except Exception as e:
            current_app.logger.error(f"Failed to generate thumbnail for evidence {ev.id}: {e}")
        
        # If still no thumbnail could be generated, return a generic error
        current_app.logger.error(f"Could not generate thumbnail for evidence {ev.id}, category: {ev.category}, file_path: {ev.file_path}")
        abort(404, "Thumbnail not available")

@evidence_bp.route("/admin/evidence/<int:submission_id>/<int:evidence_id>")
@admin_required
def admin_get_evidence(submission_id: int, evidence_id: int):
    """Admin route to view original evidence files"""
    ev = Evidence.query.filter_by(id=evidence_id, submission_id=submission_id).first_or_404()
    
    # Validate file path to prevent path traversal
    safe_path = os.path.abspath(ev.file_path)
    upload_base = os.path.abspath(current_app.config["BASE_UPLOAD_DIR"])
    
    # Ensure file is within upload directory
    if not safe_path.startswith(upload_base):
        abort(404, "File not found")
    
    # Ensure file exists
    if not os.path.exists(safe_path):
        abort(404, "File not found")
    
    directory, filename = os.path.dirname(safe_path), os.path.basename(safe_path)
    return send_from_directory(directory, filename, as_attachment=False)

@evidence_bp.route("/admin/appeal/evidence/<int:appeal_id>/<int:evidence_id>")
@admin_required
def admin_get_appeal_evidence(appeal_id: int, evidence_id: int):
    """Admin route to view appeal evidence files"""
    ev = AppealEvidence.query.filter_by(id=evidence_id, appeal_id=appeal_id).first_or_404()
    
    # Validate file path to prevent path traversal
    safe_path = os.path.abspath(ev.file_path)
    upload_base = os.path.abspath(current_app.config["BASE_UPLOAD_DIR"])
    
    # Ensure file is within upload directory
    if not safe_path.startswith(upload_base):
        abort(404, "File not found")
    
    # Ensure file exists
    if not os.path.exists(safe_path):
        abort(404, "File not found")
    
    directory, filename = os.path.dirname(safe_path), os.path.basename(safe_path)
    return send_from_directory(directory, filename, as_attachment=False)

@evidence_bp.route("/admin/appeal/evidence/<int:appeal_id>/<int:evidence_id>/thumbnail")
@admin_required
def admin_get_appeal_evidence_thumbnail(appeal_id: int, evidence_id: int):
    """Admin route to view appeal evidence thumbnails"""
    ev = AppealEvidence.query.filter_by(id=evidence_id, appeal_id=appeal_id).first_or_404()
    
    if not ev.thumbnail_path or not os.path.exists(ev.thumbnail_path):
        abort(404, "Thumbnail not found")
    
    # Validate file path to prevent path traversal
    safe_path = os.path.abspath(ev.thumbnail_path)
    upload_base = os.path.abspath(current_app.config["BASE_UPLOAD_DIR"])
    
    # Ensure file is within upload directory
    if not safe_path.startswith(upload_base):
        abort(404, "File not found")
    
    directory, filename = os.path.dirname(safe_path), os.path.basename(safe_path)
    return send_from_directory(directory, filename, as_attachment=False)

def init_evidence_routes(database_instance, models, functions):
    """Initialize evidence routes with required dependencies"""
    global db, ReviewStatus, Evidence, AppealEvidence, generate_document_placeholder
    
    db = database_instance
    ReviewStatus = models['ReviewStatus']
    Evidence = models['Evidence']
    AppealEvidence = models['AppealEvidence']
    generate_document_placeholder = functions['generate_document_placeholder']
    
    return evidence_bp