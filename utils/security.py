"""
Security utilities for NYU Dating Copilot

This module contains security-related functions including rate limiting,
session management, file validation, and content sanitization.
"""

import time
import hashlib
import hmac
import magic
import bleach
from collections import defaultdict
from flask import session, current_app as app
from werkzeug.utils import secure_filename

# Session configuration
SESSION_TIMEOUT = 1800  # 30分钟


class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)
        self.blocked_ips = {}
    
    def is_allowed(self, ip: str, limit: int = 60, window: int = 300, block_duration: int = 3600) -> bool:
        """
        检查IP是否允许访问
        :param ip: IP地址
        :param limit: 时间窗口内允许的最大请求数
        :param window: 时间窗口（秒）
        :param block_duration: 封禁持续时间（秒）
        """
        current_time = time.time()
        
        # 检查是否被封禁
        if ip in self.blocked_ips:
            if current_time - self.blocked_ips[ip] < block_duration:
                return False
            else:
                # 封禁时间已过，移除封禁
                del self.blocked_ips[ip]
        
        # 清理过期请求记录
        self.requests[ip] = [req_time for req_time in self.requests[ip] 
                           if current_time - req_time < window]
        
        # 检查请求是否超限
        if len(self.requests[ip]) >= limit:
            # 封禁IP
            self.blocked_ips[ip] = current_time
            app.logger.warning(f"IP {ip} blocked due to rate limiting. Requests in window: {len(self.requests[ip])}")
            return False
        
        # 记录当前请求
        self.requests[ip].append(current_time)
        return True
    
    def get_remaining_attempts(self, ip: str, limit: int = 60, window: int = 300) -> int:
        """获取剩余允许的请求次数"""
        current_time = time.time()
        self.requests[ip] = [req_time for req_time in self.requests[ip] 
                           if current_time - req_time < window]
        return max(0, limit - len(self.requests[ip]))


def clean_expired_sessions():
    """清理过期的session数据"""
    current_time = time.time()
    
    # 清理过期的搜索session
    search_session = session.get('accessible_search_ids')
    if search_session and current_time - search_session.get('timestamp', 0) > SESSION_TIMEOUT:
        session.pop('accessible_search_ids', None)
        app.logger.info("Cleaned expired search session")
    
    # 清理过期的首页session
    homepage_session = session.get('accessible_homepage_ids')
    if homepage_session and current_time - homepage_session.get('timestamp', 0) > SESSION_TIMEOUT:
        session.pop('accessible_homepage_ids', None)
        app.logger.info("Cleaned expired homepage session")


def validate_file_security(file, file_type):
    """Validate file extension, MIME type, and size for security"""
    if not file or not file.filename:
        return False, "No file provided"
    
    filename = secure_filename(file.filename)
    if not filename:
        return False, "Invalid filename"
    
    # Import allowed_file function from file_handler
    from .file_handler import allowed_file
    
    # Check file extension
    if file_type == 'image':
        if not allowed_file(filename, app.config['ALLOWED_IMAGE_EXTENSIONS']):
            return False, "Invalid image file extension"
        allowed_mimes = app.config['ALLOWED_IMAGE_MIMES']
        max_size = app.config['MAX_IMAGE_SIZE']
    elif file_type == 'doc':
        if not allowed_file(filename, app.config['ALLOWED_DOC_EXTENSIONS']):
            return False, "Invalid document file extension"
        allowed_mimes = app.config['ALLOWED_DOC_MIMES']
        max_size = app.config['MAX_DOC_SIZE']
    elif file_type == 'video':
        if not allowed_file(filename, app.config['ALLOWED_VIDEO_EXTENSIONS']):
            return False, "Invalid video file extension"
        allowed_mimes = app.config['ALLOWED_VIDEO_MIMES']
        max_size = app.config['MAX_VIDEO_SIZE']
    else:
        return False, "Unknown file type"
    
    # Check file size
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Seek back to beginning
    
    if file_size > max_size:
        return False, f"File too large (max {max_size // (1024*1024)}MB)"
    
    # Check MIME type using python-magic
    try:
        file_data = file.read(1024)  # Read first 1KB
        file.seek(0)  # Reset file pointer
        mime_type = magic.from_buffer(file_data, mime=True)
        
        if mime_type not in allowed_mimes:
            # 添加调试信息
            app.logger.warning(f"MIME type mismatch: got {mime_type}, allowed: {allowed_mimes}")
            return False, f"Invalid file type: {mime_type} (allowed: {', '.join(allowed_mimes)})"
    except Exception:
        return False, "Could not determine file type"
    
    return True, "Valid file"


def sanitize_html(text):
    """Sanitize HTML content to prevent XSS"""
    allowed_tags = ['br', 'p', 'strong', 'em', 'u']
    allowed_attributes = {}
    return bleach.clean(text, tags=allowed_tags, attributes=allowed_attributes, strip=True)


def generate_email_access_token(submission_id: int, email: str, secret_key: str = None) -> str:
    """
    为邮件访问生成安全token
    使用提交ID、邮箱和密钥生成HMAC
    """
    if secret_key is None:
        try:
            secret_key = app.config.get('SECRET_KEY', 'default-key')
        except RuntimeError:
            secret_key = 'default-key'  # fallback for testing
    
    data = f"{submission_id}:{email.lower().strip()}"
    token = hmac.new(
        secret_key.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()[:16]  # 取前16位作为token
    return token


def verify_email_access_token(submission_id: int, email: str, token: str, secret_key: str = None) -> bool:
    """
    验证邮件访问token是否有效
    """
    expected_token = generate_email_access_token(submission_id, email, secret_key)
    return hmac.compare_digest(expected_token, token)