"""
Decorators for NYU Dating Copilot

This module contains decorator functions for authentication,
rate limiting, and other cross-cutting concerns.
"""

from functools import wraps
from flask import session, redirect, url_for, request, current_app as app, abort


def admin_required(view_func):
    """Decorator to require admin authentication"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        from flask import current_app
        current_app.logger.info(f"Admin required check for {view_func.__name__}: is_admin={session.get('is_admin')}")
        if not session.get("is_admin"):
            current_app.logger.info(f"Admin auth failed, redirecting to login")
            return redirect(url_for("admin.admin_login", next=request.path))
        current_app.logger.info(f"Admin auth passed, calling {view_func.__name__}")
        return view_func(*args, **kwargs)

    return wrapper


def rate_limit(limit: int = 60, window: int = 300, per_route: bool = False):
    """
    Rate limiting装饰器
    :param limit: 时间窗口内允许的最大请求数
    :param window: 时间窗口（秒）
    :param per_route: 是否按路由单独计算限制
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            # Import rate_limiter from app context
            from flask import current_app
            rate_limiter = current_app.rate_limiter
            
            user_ip = request.headers.get("CF-Connecting-IP") or request.remote_addr
            
            # 如果按路由计算，IP标识包含路由名
            ip_key = f"{user_ip}:{view_func.__name__}" if per_route else user_ip
            
            if not rate_limiter.is_allowed(ip_key, limit, window):
                app.logger.warning(f"Rate limit exceeded for {user_ip} on {view_func.__name__}")
                abort(429)
            
            return view_func(*args, **kwargs)
        return wrapper
    return decorator