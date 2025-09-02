"""
Appeal models for NYU CLASS Professor Review System

This module contains Appeal and AppealEvidence models for appeals system.
"""

from datetime import datetime

def create_appeal_models(db):
    """Create and return Appeal and AppealEvidence model classes"""
    
    class Appeal(db.Model):
        __tablename__ = "appeals"

        id = db.Column(db.Integer, primary_key=True)
        submission_id = db.Column(
            db.Integer, db.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
        )
        email = db.Column(db.String(255), nullable=False)
        reason = db.Column(db.Text, nullable=False)
        status = db.Column(db.String(32), default="pending", nullable=False)  # pending | resolved | rejected
        admin_notes = db.Column(db.Text, nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
        
        # 新增字段
        appeal_evidences = db.relationship("AppealEvidence", backref="appeal", cascade="all, delete-orphan")

    class AppealEvidence(db.Model):
        __tablename__ = "appeal_evidences"

        id = db.Column(db.Integer, primary_key=True)
        appeal_id = db.Column(
            db.Integer, db.ForeignKey("appeals.id", ondelete="CASCADE"), nullable=False, index=True
        )
        category = db.Column(db.String(32), default="google_drive", nullable=False)  # google_drive
        drive_link = db.Column(db.String(2048), nullable=False)  # Google Drive link
        description = db.Column(db.Text, nullable=True)  # User-provided description/context for this evidence
        created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    return Appeal, AppealEvidence