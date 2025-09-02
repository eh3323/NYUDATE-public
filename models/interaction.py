"""
Interaction models for NYU CLASS Professor Review System

This module contains Like and Comment models for user interactions.
"""

from datetime import datetime

def create_interaction_models(db):
    """Create and return Like and Comment model classes"""
    
    class Like(db.Model):
        __tablename__ = "likes"

        id = db.Column(db.Integer, primary_key=True)
        submission_id = db.Column(
            db.Integer, db.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
        )
        user_ip = db.Column(db.String(45), nullable=False, index=True)  # IPv4/IPv6 address
        user_agent_hash = db.Column(db.String(64), nullable=False)  # MD5 hash of user agent for additional uniqueness
        created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
        
        __table_args__ = (db.UniqueConstraint('submission_id', 'user_ip', 'user_agent_hash', name='unique_like_per_user'),)

    class Comment(db.Model):
        __tablename__ = "comments"

        id = db.Column(db.Integer, primary_key=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
        submission_id = db.Column(
            db.Integer, db.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True
        )
        parent_id = db.Column(db.Integer, db.ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, index=True)  # 回复的评论ID，NULL表示顶级评论
        content = db.Column(db.Text, nullable=False)
        status = db.Column(db.String(32), default="pending", nullable=False, index=True)  # pending, approved, rejected
        client_notice = db.Column(db.Text, nullable=True)
        deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)  # 软删除标记
        user_ip = db.Column(db.String(45), nullable=True, index=True)  # 用户IP地址，支持IPv6
        
        # 关系定义
        parent = db.relationship("Comment", remote_side=[id], backref=db.backref("replies", cascade="all, delete-orphan"))
    
    return Like, Comment