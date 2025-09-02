import os
import secrets
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://nyuclass:nyuclass@localhost:5432/nyuclass",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "512")) * 1024 * 1024

    # Runtime environment & security
    FLASK_ENV = os.getenv("FLASK_ENV", "")
    FORCE_HTTPS = os.getenv("FORCE_HTTPS", "True" if FLASK_ENV.lower() == "production" else "False").lower() in {"1", "true", "yes"}
    BEHIND_PROXY = os.getenv("BEHIND_PROXY", "False").lower() in {"1", "true", "yes"}
    PREFERRED_URL_SCHEME = "https" if FORCE_HTTPS else "http"
    SESSION_COOKIE_SECURE = FORCE_HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    WTF_CSRF_TIME_LIMIT = int(os.getenv("WTF_CSRF_TIME_LIMIT_SEC", "7200"))
    # 开发模式下的CSRF设置
    WTF_CSRF_SSL_STRICT = FORCE_HTTPS
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = int(os.getenv("PERMANENT_SESSION_LIFETIME", "86400"))  # 24 hours default
    STRICT_MIME_CHECK = os.getenv("STRICT_MIME_CHECK", "True").lower() in {"1", "true", "yes"}

    # Upload directories
    BASE_UPLOAD_DIR = os.getenv(
        "UPLOAD_DIR",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "uploads")),
    )
    IMAGE_UPLOAD_DIR = os.path.join(BASE_UPLOAD_DIR, "images")
    DOC_UPLOAD_DIR = os.path.join(BASE_UPLOAD_DIR, "documents")
    VIDEO_UPLOAD_DIR = os.path.join(BASE_UPLOAD_DIR, "videos")
    THUMBNAIL_UPLOAD_DIR = os.path.join(BASE_UPLOAD_DIR, "thumbnails")

    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "pbkdf2:sha256:600000$default$changeme")  # Password hash - update in production

    # Allowed file extensions and MIME types
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
    ALLOWED_DOC_EXTENSIONS = {"pdf", "txt", "doc", "docx"}
    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "mov", "m4v", "webm"}
    
    # MIME type validation for security
    ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif"}
    ALLOWED_DOC_MIMES = {"application/pdf", "text/plain", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    ALLOWED_VIDEO_MIMES = {
        "video/mp4", "video/quicktime", "video/webm", 
        "video/x-msvideo", "video/avi", "video/x-ms-wmv",
        "video/mp4v-es", "application/mp4"  # 一些系统可能返回这些MIME类型
    }
    
    # File size limits (in bytes)
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_DOC_SIZE = 50 * 1024 * 1024   # 50MB  
    MAX_VIDEO_SIZE = 100 * 1024 * 1024 # 100MB
    
    # File quantity limits
    MAX_IMAGES_PER_SUBMISSION = 10  # 最多10张图片
    MAX_DOCS_PER_SUBMISSION = 5     # 最多5个文档
    MAX_VIDEOS_PER_SUBMISSION = 3   # 最多3个视频
    
    # File total size limits
    MAX_IMAGES_TOTAL_SIZE = 20 * 1024 * 1024   # 图片总大小20MB
    MAX_DOCS_TOTAL_SIZE = 20 * 1024 * 1024     # 文档总大小20MB
    MAX_VIDEOS_TOTAL_SIZE = 20 * 1024 * 1024   # 视频总大小20MB

    # Mail settings
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() in {"1", "true", "yes"}
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")
    
    # Base URL for email templates and external links
    BASE_URL = os.getenv("BASE_URL", "https://localhost:5000")

    # Cloudflare Turnstile
    TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY")
    TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET")

    # Rate limiting storage (using memory storage)
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

    # Privacy protection settings
    THUMBNAIL_SIZE = (300, 300)  # Maximum thumbnail dimensions
    THUMBNAIL_QUALITY = 75  # JPEG quality for thumbnails
    BLUR_RADIUS = 6  # Blur radius for privacy protection
    
    # OpenAI API settings for content moderation
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")  
    OPENAI_API_TIMEOUT = int(os.getenv("OPENAI_API_TIMEOUT", "30"))  # API timeout in seconds
    CONTENT_MODERATION_ENABLED = os.getenv("CONTENT_MODERATION_ENABLED", "True").lower() in {"1", "true", "yes"}
    OPENAI_CLEAR_PROXIES = os.getenv("OPENAI_CLEAR_PROXIES", "False").lower() in {"1", "true", "yes"}
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")  # Optional: custom endpoint
    OPENAI_USE_CUSTOM_HTTP_CLIENT = os.getenv("OPENAI_USE_CUSTOM_HTTP_CLIENT", "False").lower() in {"1", "true", "yes"}
