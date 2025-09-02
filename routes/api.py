"""
API routes for NYU CLASS Professor Review System

This module contains all API endpoints including likes, comments, and admin API routes.
"""

import hashlib
import time
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
# CSRF will be handled by the main app's csrf.exempt decorator
from sqlalchemy import func
from utils.decorators import admin_required, rate_limit
from utils.security import sanitize_html

# This will be set by the main app
db = None
ReviewStatus = None
Submission = None
Like = None
Comment = None
moderate_content = None

# Create API blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

def get_user_fingerprint(request):
    """生成用户指纹用于点赞去重"""
    user_ip = request.headers.get("CF-Connecting-IP") or request.remote_addr or "unknown"
    user_agent = request.headers.get("User-Agent", "")
    user_agent_hash = hashlib.md5(user_agent.encode('utf-8')).hexdigest()
    return user_ip, user_agent_hash

@api_bp.route("/like/<int:submission_id>", methods=["POST"])
@rate_limit(limit=10, window=60)  # 10 per minute
def toggle_like(submission_id: int):
    """切换点赞状态"""
    try:
        # 检查提交是否存在且已审核通过
        submission = Submission.query.filter_by(id=submission_id, status=ReviewStatus.APPROVED).first()
        if not submission:
            return jsonify({"error": "记录不存在或未审核通过"}), 404
        
        # 获取用户指纹
        user_ip, user_agent_hash = get_user_fingerprint(request)
        
        # 检查是否已经点赞
        existing_like = Like.query.filter_by(
            submission_id=submission_id,
            user_ip=user_ip,
            user_agent_hash=user_agent_hash
        ).first()
        
        if existing_like:
            # 取消点赞
            db.session.delete(existing_like)
            liked = False
        else:
            # 添加点赞
            new_like = Like(
                submission_id=submission_id,
                user_ip=user_ip,
                user_agent_hash=user_agent_hash
            )
            db.session.add(new_like)
            liked = True
        
        db.session.commit()
        
        # 更新缓存的点赞数
        submission.update_like_count()
        
        # 返回最新的点赞数
        like_count = submission.like_count
        
        return jsonify({
            "liked": liked,
            "like_count": like_count
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"点赞操作失败: {e}")
        return jsonify({"error": "操作失败"}), 500

@api_bp.route("/like-status/<int:submission_id>", methods=["GET"])
@rate_limit(limit=30, window=60)  # 30 per minute
def get_like_status(submission_id: int):
    """获取用户对特定提交的点赞状态"""
    try:
        # 检查提交是否存在且已审核通过
        submission = Submission.query.filter_by(id=submission_id, status=ReviewStatus.APPROVED).first()
        if not submission:
            return jsonify({"error": "记录不存在或未审核通过"}), 404
        
        # 获取用户指纹
        user_ip, user_agent_hash = get_user_fingerprint(request)
        
        # 检查用户是否已经点赞
        existing_like = Like.query.filter_by(
            submission_id=submission_id,
            user_ip=user_ip,
            user_agent_hash=user_agent_hash
        ).first()
        
        return jsonify({
            "liked": existing_like is not None,
            "like_count": submission.like_count
        })
        
    except Exception as e:
        current_app.logger.error(f"获取点赞状态失败: {e}")
        return jsonify({"error": "操作失败"}), 500

@api_bp.route("/comments/<int:submission_id>", methods=["GET"])
@rate_limit(limit=60, window=60)  # 60 per minute  
def get_comments(submission_id: int):
    """获取评论"""
    try:
        # 检查提交是否存在且已审核通过
        submission = Submission.query.filter_by(id=submission_id, status=ReviewStatus.APPROVED).first()
        if not submission:
            return jsonify({"error": "记录不存在或未审核通过"}), 404
        
        # 获取已通过审核且未删除的评论
        comments = Comment.query.filter_by(
            submission_id=submission_id,
            status="approved",
            deleted=False
        ).order_by(Comment.created_at.asc()).all()
        
        # 构建评论树
        comment_dict = {}
        root_comments = []
        
        for comment in comments:
            comment_data = {
                "id": comment.id,
                "content": comment.content,
                "created_at": comment.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "replies": []
            }
            comment_dict[comment.id] = comment_data
            
            if comment.parent_id is None:
                root_comments.append(comment_data)
            elif comment.parent_id in comment_dict:
                comment_dict[comment.parent_id]["replies"].append(comment_data)
        
        return jsonify({
            "comments": root_comments,
            "total": len(comments)
        })
        
    except Exception as e:
        current_app.logger.error(f"获取评论失败: {e}")
        return jsonify({"error": "操作失败"}), 500

@api_bp.route("/comments", methods=["POST"])
def submit_comment():
    """提交评论"""
    try:
        # 获取表单数据
        submission_id = request.json.get("submission_id")
        content = request.json.get("content", "").strip()
        parent_id = request.json.get("parent_id")
        
        # 基本验证
        if not submission_id or not content:
            return jsonify({"error": "缺少必填字段"}), 400
        
        if len(content) > 500:
            return jsonify({"error": "评论内容过长"}), 400
        
        # 检查提交是否存在且已审核通过
        submission = Submission.query.filter_by(id=submission_id, status=ReviewStatus.APPROVED).first()
        if not submission:
            return jsonify({"error": "记录不存在或未审核通过"}), 404
        
        # 检查父评论是否存在（如果是回复）
        if parent_id:
            parent_comment = Comment.query.filter_by(id=parent_id, submission_id=submission_id, deleted=False).first()
            if not parent_comment:
                return jsonify({"error": "父评论不存在"}), 404
        
        # 获取用户IP
        user_ip = request.headers.get("CF-Connecting-IP") or request.remote_addr or "unknown"
        
        # 速率限制：每IP每分钟最多3条评论
        recent_comments = Comment.query.filter(
            Comment.user_ip == user_ip,
            Comment.created_at > datetime.utcnow() - timedelta(minutes=1)
        ).count()
        
        if recent_comments >= 3:
            return jsonify({"error": "评论过于频繁，请稍后再试"}), 429
        
        # 清理HTML内容
        clean_content = sanitize_html(content)
        
        # 内容审核
        moderation_result = moderate_content(clean_content)
        
        # 根据审核结果决定状态
        if moderation_result['action'] == 'BLOCK':
            return jsonify({"error": "评论内容违反社区规范"}), 400
        
        comment_status = "approved" if moderation_result['action'] == 'ALLOW' else "pending"
        client_notice = moderation_result.get('client_notice', '')
        
        # 创建评论
        comment = Comment(
            submission_id=submission_id,
            parent_id=parent_id,
            content=clean_content,
            status=comment_status,
            client_notice=client_notice,
            user_ip=user_ip
        )
        
        db.session.add(comment)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "评论提交成功" if comment_status == "approved" else "评论已提交，等待审核",
            "status": comment_status,
            "notice": client_notice
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"评论提交失败: {e}")
        return jsonify({"error": "提交失败"}), 500

@api_bp.route("/admin/comments/<int:comment_id>", methods=["DELETE"])
@admin_required
def admin_delete_comment(comment_id: int):
    """管理员删除评论"""
    try:
        comment = Comment.query.get_or_404(comment_id)
        
        # 软删除：设置deleted=True而不是物理删除
        comment.deleted = True
        
        db.session.commit()
        
        return jsonify({"message": "评论已删除"})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"删除评论失败: {e}")
        return jsonify({"error": "删除失败"}), 500

@api_bp.route("/admin/comments/<int:submission_id>", methods=["GET"])
@admin_required
def admin_get_comments(submission_id: int):
    """管理员获取评论（包括未审核的）"""
    try:
        comments = Comment.query.filter_by(
            submission_id=submission_id,
            deleted=False
        ).order_by(Comment.created_at.desc()).all()
        
        comment_list = []
        for comment in comments:
            comment_data = {
                "id": comment.id,
                "content": comment.content,
                "status": comment.status,
                "created_at": comment.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "user_ip": comment.user_ip,
                "parent_id": comment.parent_id,
                "client_notice": comment.client_notice
            }
            comment_list.append(comment_data)
        
        return jsonify({
            "comments": comment_list,
            "total": len(comment_list)
        })
        
    except Exception as e:
        current_app.logger.error(f"获取评论失败: {e}")
        return jsonify({"error": "获取失败"}), 500

def init_api_routes(database_instance, models, moderate_content_func):
    """Initialize API routes with required dependencies"""
    global db, ReviewStatus, Submission, Like, Comment, moderate_content
    db = database_instance
    ReviewStatus = models['ReviewStatus']
    Submission = models['Submission']
    Like = models['Like']
    Comment = models['Comment']
    moderate_content = moderate_content_func
    
    return api_bp