"""
Evidence model for NYU CLASS Professor Review System

This module contains the Evidence model for file attachments.
"""

def create_evidence_model(db):
    """Create and return Evidence model class"""
    
    class Evidence(db.Model):
        __tablename__ = "evidences"

        id = db.Column(db.Integer, primary_key=True)
        submission_id = db.Column(
            db.Integer, db.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
        )
        category = db.Column(db.String(32), nullable=False)  # image | document | video | chat_video | chat_image
        file_path = db.Column(db.String(1024), nullable=False)
        original_filename = db.Column(db.String(512), nullable=False)
        mime_type = db.Column(db.String(255), nullable=True)
        file_size = db.Column(db.Integer, nullable=True)
        thumbnail_path = db.Column(db.String(1024), nullable=True)  # Path to privacy-protected thumbnail
        description = db.Column(db.Text, nullable=True)  # User-provided description/context for this evidence
    
    return Evidence