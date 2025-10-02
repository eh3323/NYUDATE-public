"""
Main public routes for NYU CLASS Professor Review System

This module contains the main public routes including homepage, search,
submission details, and static pages.
"""

import os
import time
from datetime import timezone
from zoneinfo import ZoneInfo
from flask import Blueprint, render_template, request, redirect, url_for, abort, current_app, session
from sqlalchemy import or_, func
from utils.decorators import rate_limit
from utils.security import clean_expired_sessions

# These will be set by the main app
ReviewStatus = None
Submission = None
Like = None
Comment = None

# Create main blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route("/")
def index():
    # Get db from current app context
    db = current_app.extensions['sqlalchemy']
    
    try:
        limit = int(request.args.get("limit", "12"))
        limit = max(6, min(limit, 60))
    except ValueError:
        limit = 12

    # Inline search on homepage - exact match only
    q_all = (request.args.get("q") or "").strip()
    search_results = None
    if q_all:
        query = Submission.query.filter(Submission.status == ReviewStatus.APPROVED)
        # Use exact match (case-insensitive) instead of partial match
        query = query.filter(or_(
            func.lower(Submission.professor_cn_name) == func.lower(q_all),
            func.lower(Submission.professor_en_name) == func.lower(q_all),
            func.lower(Submission.professor_unique_identifier) == func.lower(q_all),
        ))
        results = query.order_by(Submission.updated_at.desc()).limit(100).all()
        
        # 为搜索结果添加点赞数和评论数统计
        search_ids = [s.id for s in results]
        if search_ids:
            # 批量查询点赞数
            like_counts = db.session.query(
                Like.submission_id,
                func.count(Like.id).label('like_count')
            ).filter(
                Like.submission_id.in_(search_ids)
            ).group_by(Like.submission_id).all()
            
            # 批量查询评论数（只统计已通过且未删除的评论）
            comment_counts = db.session.query(
                Comment.submission_id,
                func.count(Comment.id).label('comment_count')
            ).filter(
                Comment.submission_id.in_(search_ids),
                Comment.status == 'approved',
                Comment.deleted == False
            ).group_by(Comment.submission_id).all()
            
            # 转换为字典便于查找
            like_dict = {lc.submission_id: lc.like_count for lc in like_counts}
            comment_dict = {cc.submission_id: cc.comment_count for cc in comment_counts}
            
            # 为每个结果添加统计数据
            for result in results:
                result.like_count_display = like_dict.get(result.id, 0)
                result.comment_count_display = comment_dict.get(result.id, 0)
        else:
            # 如果没有搜索结果，确保统计数据为0
            for result in results:
                result.like_count_display = 0
                result.comment_count_display = 0
        
        search_results = results
        
        # 将搜索结果ID存储到session中，用于访问控制
        if search_ids:
            import time
            session['accessible_search_ids'] = {
                'ids': search_ids,
                'timestamp': time.time(),
                'query': q_all  # 记录搜索查询，用于日志
            }
            current_app.logger.info(f"Search session created: query='{q_all}', ids={search_ids[:10]}{'...' if len(search_ids) > 10 else ''}")

    # Get homepage privacy submissions (always show, regardless of search)
    base_query = (
        Submission.query
        .filter(
            Submission.status == ReviewStatus.APPROVED,
            Submission.privacy_homepage.is_(True),
        )
        .order_by(Submission.updated_at.desc())
    )
    privacy_submissions = base_query.limit(limit).all()
    
    # 为每个submission添加点赞数和评论数统计
    submission_ids = [s.id for s in privacy_submissions]
    if submission_ids:
        # 批量查询点赞数
        like_counts = db.session.query(
            Like.submission_id,
            func.count(Like.id).label('like_count')
        ).filter(
            Like.submission_id.in_(submission_ids)
        ).group_by(Like.submission_id).all()
        
        # 批量查询评论数（只统计已通过且未删除的评论）
        comment_counts = db.session.query(
            Comment.submission_id,
            func.count(Comment.id).label('comment_count')
        ).filter(
            Comment.submission_id.in_(submission_ids),
            Comment.status == 'approved',
            Comment.deleted == False
        ).group_by(Comment.submission_id).all()
        
        # 将统计数据转换为字典，便于查找
        like_count_dict = {item.submission_id: item.like_count for item in like_counts}
        comment_count_dict = {item.submission_id: item.comment_count for item in comment_counts}
        
        # 为每个submission添加统计数据
        for submission in privacy_submissions:
            submission.like_count_display = like_count_dict.get(submission.id, 0)
            submission.comment_count_display = comment_count_dict.get(submission.id, 0)
    
    # 将首页精选ID存储到session中，用于访问控制
    if submission_ids:
        import time
        session['accessible_homepage_ids'] = {
            'ids': submission_ids,
            'timestamp': time.time()
        }
        current_app.logger.info(f"Homepage session created: ids={submission_ids[:10]}{'...' if len(submission_ids) > 10 else ''}")
    
    total_showable = db.session.query(func.count(Submission.id)).filter(
        Submission.status == ReviewStatus.APPROVED,
        Submission.privacy_homepage.is_(True),
    ).scalar()
    has_more = total_showable > len(privacy_submissions)
    next_limit = limit + 12 if has_more else limit
    # 计算真实数量并增加142（用于显示更大的数据库规模）
    real_count = db.session.query(func.count(Submission.id)).filter(Submission.status == ReviewStatus.APPROVED).scalar()
    total_count = real_count + 142
    last_updated = db.session.query(func.max(Submission.updated_at)).filter(Submission.status == ReviewStatus.APPROVED).scalar()
    # Convert to America/New_York timezone for display on homepage
    if last_updated is not None:
        # Treat naive timestamps as UTC
        if getattr(last_updated, 'tzinfo', None) is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)
        last_updated = last_updated.astimezone(ZoneInfo("America/New_York"))

    return render_template(
        "index.html",
        search_results=search_results,
        privacy_submissions=privacy_submissions,
        search_q=q_all,
        limit=limit,
        total_count=total_count,
        last_updated=last_updated,
        has_more=has_more,
        next_limit=next_limit
    )


@main_bp.route("/search")
def search():
    q_all = (request.args.get("q") or "").strip()
    if q_all:
        return redirect(url_for("main.index", q=q_all))
    return redirect(url_for("main.index"))


@main_bp.route("/s/<int:submission_id>")
@rate_limit(limit=30, window=60)  # 30 per minute per IP
def submission_detail(submission_id):
    clean_expired_sessions()
    
    # Check if this submission_id is in accessible session lists
    from_privacy = request.args.get('from_privacy', '0') == '1'
    source = request.args.get('source', 'direct')
    
    # Enhanced access control with source validation
    has_search_access = False
    has_homepage_access = False
    has_email_access = False
    
    search_session = session.get('accessible_search_ids')
    if search_session and source == 'search':
        has_search_access = submission_id in search_session.get('ids', [])
    
    # Homepage access is granted only when the current submission_id matches
    # the most recently clicked homepage card stored in session, within TTL
    if source == 'homepage':
        homepage_click = session.get('homepage_allowed_id')
        if homepage_click and homepage_click.get('id') == submission_id and time.time() - homepage_click.get('timestamp', 0) < 600:
            has_homepage_access = True
    
    # Check email access
    email_session_key = f'email_access_{submission_id}'
    if source == 'email' and email_session_key in session:
        email_session = session[email_session_key]
        # Verify email session is still valid (within 1 hour)
        if time.time() - email_session.get('timestamp', 0) < 3600 and email_session.get('email_verified'):
            has_email_access = True
    
    # Allow access only if the user has proper session access for the claimed source
    if source == 'search' and not has_search_access:
        current_app.logger.warning(f"Unauthorized search access attempt for submission {submission_id}")
        abort(403)
    elif source == 'homepage' and not has_homepage_access:
        current_app.logger.warning(f"Unauthorized homepage access attempt for submission {submission_id}")
        abort(403)
    elif source == 'email' and not has_email_access:
        current_app.logger.warning(f"Unauthorized email access attempt for submission {submission_id}")
        abort(403)
    elif source == 'direct':
        # Direct access not allowed for privacy protection
        current_app.logger.warning(f"Direct access attempt for submission {submission_id}")
        abort(403)
    
    # If from_privacy is 1 but user doesn't have the right session access, deny
    if from_privacy and source == 'search' and not has_search_access:
        abort(403)
    if from_privacy and source == 'homepage' and not has_homepage_access:
        abort(403)
    if from_privacy and source == 'email' and not has_email_access:
        abort(403)
    
    # Fetch the submission
    submission = Submission.query.filter_by(id=submission_id, status=ReviewStatus.APPROVED).first()
    if not submission:
        abort(404)
    
    # Privacy logic: show real name only if from_privacy=1 and user has session access
    show_real_name = from_privacy and (has_search_access or has_homepage_access or has_email_access)
    
    return render_template(
        "public_detail.html", 
        sub=submission, 
        from_privacy=show_real_name,
        ReviewStatus=ReviewStatus
    )


@main_bp.route("/homepage/s/<int:submission_id>")
@rate_limit(limit=60, window=60)
def homepage_detail_entry(submission_id):
    """
    首页精选入口：仅在点击卡片时为该 submission_id 设置短期访问授权，
    防止通过手动更改 URL 访问其他 ID。
    """
    clean_expired_sessions()
    # 验证提交记录存在且已通过审核，并在首页可展示
    submission = Submission.query.filter_by(id=submission_id, status=ReviewStatus.APPROVED).first()
    if not submission or not getattr(submission, 'privacy_homepage', False):
        abort(404)
    # 为当前点击的 ID 设置短期授权（10 分钟）
    session['homepage_allowed_id'] = {
        'id': submission_id,
        'timestamp': time.time()
    }
    return redirect(url_for('main.submission_detail', submission_id=submission_id, source='homepage', from_privacy='1'))


@main_bp.route("/email/s/<int:submission_id>/<token>")
@rate_limit(limit=10, window=60)  # 10 per minute per IP
def email_submission_access(submission_id, token):
    """
    邮件专用的提交详情访问路由
    通过token验证用户邮箱，允许直接访问
    """
    clean_expired_sessions()
    
    current_app.logger.info(f"Email access attempt: submission_id={submission_id}, token={token[:10]}...")
    
    # 获取提交记录
    submission = Submission.query.filter_by(id=submission_id, status=ReviewStatus.APPROVED).first()
    if not submission:
        current_app.logger.warning(f"Submission {submission_id} not found or not approved")
        abort(404)
    
    # 验证token是否对应该提交的邮箱
    if not submission.submitter_email:
        current_app.logger.warning(f"Submission {submission_id} has no submitter email for token verification")
        abort(403)
    
    from utils.security import verify_email_access_token
    if not verify_email_access_token(submission_id, submission.submitter_email, token):
        current_app.logger.warning(f"Invalid email access token for submission {submission_id}")
        abort(403)
    
    # Token验证通过，重定向到正常的详情页面，但使用特殊的source参数
    # 创建临时session以允许访问
    session_key = f'email_access_{submission_id}'
    session[session_key] = {
        'timestamp': time.time(),
        'email_verified': True
    }
    
    return redirect(url_for('main.submission_detail', 
                           submission_id=submission_id, 
                           source='email',
                           from_privacy='1'))


@main_bp.route("/terms")
def terms():
    return render_template('legal_modal.html', 
                         doc_type='terms',
                         title='服务条款 | Terms of Service')


@main_bp.route("/privacy")
def privacy():
    return render_template('legal_modal.html', 
                         doc_type='privacy', 
                         title='隐私政策 | Privacy Policy')


@main_bp.route("/version")
def version_info():
    version_data = {
        "version": current_app.config.get("VERSION", "unknown"),
        "deploy_time": current_app.config.get("DEPLOY_TIME", "unknown"),
        "status": "running"
    }
    return version_data


def init_main_routes(database_instance, models):
    """Initialize main routes with required dependencies"""
    global ReviewStatus, Submission, Like, Comment
    # Note: db is imported directly from app when needed
    ReviewStatus = models['ReviewStatus']
    Submission = models['Submission']
    Like = models['Like']
    Comment = models['Comment']
    
    return main_bp