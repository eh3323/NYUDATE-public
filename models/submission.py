"""
Submission model for NYU CLASS Professor Review System

This module contains the main Submission model and related constants.
"""

from datetime import datetime

class ReviewStatus:
    PENDING = "pending"
    APPROVED = "approved" 
    REJECTED = "rejected"
    HIDDEN = "hidden"


def mask_name(name: str) -> str:
    """Mask names for privacy protection"""
    if not name:
        return name
    first = name.strip()[:1]
    if not first:
        return name
    return first + "***"


def create_submission_model(db):
    """Create and return Submission model class"""
    
    class Submission(db.Model):
        __tablename__ = "submissions"

        id = db.Column(db.Integer, primary_key=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
        updated_at = db.Column(
            db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
        )

        submitter_email = db.Column(db.String(255), nullable=False)

        professor_cn_name = db.Column(db.String(255), nullable=True)
        professor_en_name = db.Column(db.String(255), nullable=True)
        professor_unique_identifier = db.Column(db.String(255), nullable=True)
        professor_birthday = db.Column(db.String(32), nullable=True)

        # 贬义标签
        tag_positive = db.Column(db.Boolean, default=False, nullable=False)  # 出轨
        tag_calm = db.Column(db.Boolean, default=False, nullable=False)  # 冷暴力  
        tag_leadership = db.Column(db.Boolean, default=False, nullable=False)  # PUA
        tag_homework_heavy = db.Column(db.Boolean, default=False, nullable=False)  # 骗钱
        
        # 褒义标签
        tag_loyal = db.Column(db.Boolean, default=False, nullable=False)  # 忠诚
        tag_stable = db.Column(db.Boolean, default=False, nullable=False)  # 情绪稳定
        tag_sincere = db.Column(db.Boolean, default=False, nullable=False)  # 真诚付出
        tag_humorous = db.Column(db.Boolean, default=False, nullable=False)  # 幽默
        
        tag_custom = db.Column(db.String(255), nullable=True)

        description = db.Column(db.Text, nullable=False)
        allow_public_evidence = db.Column(db.Boolean, default=True, nullable=False)

        privacy_homepage = db.Column(db.Boolean, default=True, nullable=False)

        status = db.Column(db.String(32), default=ReviewStatus.PENDING, index=True, nullable=False)
        admin_notes = db.Column(db.Text, nullable=True)
        flagged = db.Column(db.Boolean, default=False, nullable=False)

        evidences = db.relationship("Evidence", backref="submission", cascade="all, delete-orphan")
        appeals = db.relationship("Appeal", backref="submission", cascade="all, delete-orphan")
        likes = db.relationship("Like", backref="submission", cascade="all, delete-orphan")
        comments = db.relationship("Comment", backref="submission", cascade="all, delete-orphan")
        
        # 点赞计数缓存字段
        like_count = db.Column(db.Integer, default=0, nullable=False)

        def get_display_name(self, masked: bool = False) -> str:
            base = self.professor_cn_name or self.professor_en_name or self.professor_unique_identifier or "未知"
            if not masked:
                return base
            return mask_name(base)
        
        def get_like_count(self):
            """获取实时点赞数"""
            # Import Like dynamically to avoid circular imports
            Like = db.Model.registry._class_registry.get('Like')
            if Like:
                return Like.query.filter_by(submission_id=self.id).count()
            return 0
        
        def update_like_count(self):
            """更新点赞数缓存"""
            self.like_count = self.get_like_count()
            db.session.commit()
    
    return Submission