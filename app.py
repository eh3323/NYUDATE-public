import os
import typing
import json
from background_tasks import get_task_manager
import requests

from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect, generate_csrf
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import text

from config import Config

# Import utility functions from utils package
from utils.security import RateLimiter, clean_expired_sessions

# Import services
from services.moderation import moderate_content
from services.file_processing import generate_document_placeholder
from services.email import send_email_async
from services.thumbnails import generate_thumbnails_async

app = Flask(__name__)
app.config.from_object(Config)

# 版本信息
VERSION = "2025.08.14.001"
DEPLOY_TIME = "2025-08-14 07:31:26"

# Add custom template filters for safe HTML handling
@app.template_filter('safe_newlines')
def safe_newlines_filter(text):
    """Convert newlines to <br/> tags after HTML escaping"""
    if text is None:
        return ""
    # First escape all HTML content
    from markupsafe import escape, Markup
    escaped_text = escape(text)
    # Then convert newlines to <br/> tags and mark as safe
    result = escaped_text.replace('\n', Markup('<br/>'))
    return result

@app.template_filter('safe_email_html')
def safe_email_html_filter(text):
    """Allow only safe HTML tags in email content"""
    if text is None:
        return ""
    # Use bleach to allow only safe HTML tags for emails
    import bleach
    allowed_tags = ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'a']
    allowed_attributes = {'a': ['href']}
    cleaned = bleach.clean(text, tags=allowed_tags, attributes=allowed_attributes, strip=True)
    return cleaned

# Load translations
with open(os.path.join(os.path.dirname(__file__), 'translations.json'), 'r', encoding='utf-8') as f:
    TRANSLATIONS = json.load(f)

def get_locale():
    """Get current language from query parameter or session"""
    lang = request.args.get('lang')
    if lang in ['zh', 'en']:
        session['language'] = lang
        return lang
    return session.get('language', 'zh')

def t(key_path, **kwargs):
    """Translation helper function"""
    lang = get_locale()
    keys = key_path.split('.')
    value = TRANSLATIONS
    for key in keys:
        value = value.get(key, {})
    text = value.get(lang, value.get('zh', key_path))

    # Handle string formatting if kwargs provided
    if kwargs:
        try:
            text = text % tuple(kwargs.values())
        except:
            pass
    return text

# Inject globals into templates
@app.context_processor
def inject_globals():
    return {
        "config": app.config,
        "VERSION": VERSION,
        "DEPLOY_TIME": DEPLOY_TIME,
        "generate_csrf": generate_csrf,
        "t": t,
        "current_lang": get_locale,
    }

# Add security headers for all routes
if not app.debug:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    talisman = Talisman(
        app,
        force_https=False,
        strict_transport_security=True,
        strict_transport_security_max_age=31536000,
        content_security_policy={
            'default-src': "'self'",
            'script-src': "'self' 'unsafe-inline' challenges.cloudflare.com",
            'style-src': "'self' 'unsafe-inline' cdnjs.cloudflare.com fonts.googleapis.com",
            'font-src': "'self' fonts.gstatic.com",
            'img-src': "'self' data:",
            'connect-src': "'self'",
            'frame-src': "'self' challenges.cloudflare.com https://nyudate.com",
        },
        referrer_policy='strict-origin-when-cross-origin'
    )

# Initialize extensions
db = SQLAlchemy(app)
mail = Mail(app)
app.mail = mail  # Make mail available to utils modules
csrf = CSRFProtect(app)

# Configure session settings
from datetime import timedelta
app.permanent_session_lifetime = timedelta(seconds=app.config['PERMANENT_SESSION_LIFETIME'])

# Setup rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["1000 per day", "100 per hour"],
    storage_uri=app.config.get("RATELIMIT_STORAGE_URL", "memory://"),
)

# Global rate limiter instance
global_rate_limiter = RateLimiter()
app.rate_limiter = global_rate_limiter

# 确保所有模型在应用启动时都注册到SQLAlchemy
from models import init_models

# Create models in app context
with app.app_context():
    model_classes = init_models(db)
    
    # Make models available globally
    globals().update(model_classes)
    
    # Extract individual model classes
    ReviewStatus = model_classes['ReviewStatus']
    Submission = model_classes['Submission']
    Evidence = model_classes['Evidence']
    Appeal = model_classes['Appeal']
    AppealEvidence = model_classes['AppealEvidence']
    Like = model_classes['Like']
    Comment = model_classes['Comment']

@app.before_request
def before_request_cleanup():
    """每个请求前清理过期的session"""
    clean_expired_sessions()

def ensure_schema_migrations():
    # PostgreSQL schema migration
    db.session.execute(text(
        """
        DO $$
        BEGIN
            -- 创建申诉表
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name='appeals'
            ) THEN
                CREATE TABLE appeals (
                    id SERIAL PRIMARY KEY,
                    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
                    email VARCHAR(320) NOT NULL,
                    reason TEXT NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    admin_notes TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                CREATE INDEX idx_appeals_submission_id ON appeals(submission_id);
                CREATE INDEX idx_appeals_status ON appeals(status);
                CREATE INDEX idx_appeals_created_at ON appeals(created_at DESC);
            END IF;
            
            -- 创建证据表
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name='evidences'
            ) THEN
                CREATE TABLE evidences (
                    id SERIAL PRIMARY KEY,
                    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
                    category VARCHAR(32) NOT NULL,
                    file_path VARCHAR(1024) NOT NULL,
                    original_filename VARCHAR(512) NOT NULL,
                    mime_type VARCHAR(255),
                    file_size INTEGER,
                    thumbnail_path VARCHAR(1024),
                    description TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                CREATE INDEX idx_evidences_submission_id ON evidences(submission_id);
            END IF;

            -- 添加 allow_public_evidence 字段
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='submissions' AND column_name='allow_public_evidence'
            ) THEN
                ALTER TABLE submissions ADD COLUMN allow_public_evidence BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
            
            -- 添加 privacy_homepage 字段
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='submissions' AND column_name='privacy_homepage'
            ) THEN
                ALTER TABLE submissions ADD COLUMN privacy_homepage BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
            
            -- 添加 flagged 字段
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='submissions' AND column_name='flagged'
            ) THEN
                ALTER TABLE submissions ADD COLUMN flagged BOOLEAN NOT NULL DEFAULT FALSE;
                CREATE INDEX idx_submissions_flagged ON submissions(flagged);
            END IF;
            
            -- 添加新的标签字段
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='submissions' AND column_name='tag_loyal'
            ) THEN
                ALTER TABLE submissions ADD COLUMN tag_loyal BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='submissions' AND column_name='tag_stable'
            ) THEN
                ALTER TABLE submissions ADD COLUMN tag_stable BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='submissions' AND column_name='tag_sincere'
            ) THEN
                ALTER TABLE submissions ADD COLUMN tag_sincere BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='submissions' AND column_name='tag_humorous'
            ) THEN
                ALTER TABLE submissions ADD COLUMN tag_humorous BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
            
            -- 创建申诉证据表
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name='appeal_evidences'
            ) THEN
                CREATE TABLE appeal_evidences (
                    id SERIAL PRIMARY KEY,
                    appeal_id INTEGER NOT NULL REFERENCES appeals(id) ON DELETE CASCADE,
                    category VARCHAR(32) NOT NULL,
                    file_path VARCHAR(1024) NOT NULL,
                    original_filename VARCHAR(512) NOT NULL,
                    mime_type VARCHAR(255),
                    file_size INTEGER,
                    thumbnail_path VARCHAR(1024),
                    description TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                CREATE INDEX idx_appeal_evidences_appeal_id ON appeal_evidences(appeal_id);
            END IF;
            
            -- 创建点赞表
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name='likes'
            ) THEN
                CREATE TABLE likes (
                    id SERIAL PRIMARY KEY,
                    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
                    user_ip VARCHAR(45) NOT NULL,
                    user_agent_hash VARCHAR(64) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                CREATE INDEX idx_likes_submission_id ON likes(submission_id);
                CREATE INDEX idx_likes_user_ip ON likes(user_ip);
                CREATE UNIQUE INDEX unique_like_per_user ON likes(submission_id, user_ip, user_agent_hash);
            END IF;
            
            -- 添加点赞数缓存字段
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='submissions' AND column_name='like_count'
            ) THEN
                ALTER TABLE submissions ADD COLUMN like_count INTEGER NOT NULL DEFAULT 0;
            END IF;
            
            -- 创建评论表
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name='comments'
            ) THEN
                CREATE TABLE comments (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    client_notice TEXT
                );
                CREATE INDEX idx_comments_submission_id ON comments(submission_id);
                CREATE INDEX idx_comments_status ON comments(status);
            END IF;
            
            -- 为评论表添加软删除字段
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='comments' AND column_name='deleted'
            ) THEN
                ALTER TABLE comments ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT FALSE;
                CREATE INDEX idx_comments_deleted ON comments(deleted);
            END IF;
            
            -- 为评论表添加parent_id字段支持回复功能
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='comments' AND column_name='parent_id'
            ) THEN
                ALTER TABLE comments ADD COLUMN parent_id INTEGER NULL REFERENCES comments(id) ON DELETE CASCADE;
                CREATE INDEX idx_comments_parent_id ON comments(parent_id);
            END IF;
            
            -- 为评论表添加user_ip字段支持rate limiting
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='comments' AND column_name='user_ip'
            ) THEN
                ALTER TABLE comments ADD COLUMN user_ip VARCHAR(45) NULL;
                CREATE INDEX idx_comments_user_ip ON comments(user_ip);
            END IF;
            
            -- 首次添加字段时的初始化（已完成，注释掉避免重复执行）
            -- UPDATE submissions SET allow_public_evidence = TRUE WHERE allow_public_evidence = FALSE;
            -- UPDATE submissions SET privacy_homepage = TRUE WHERE privacy_homepage = FALSE;
        END $$;
        """
    ))

def verify_turnstile(response_token: str, remote_ip: typing.Optional[str] = None) -> bool:
    secret = app.config.get("TURNSTILE_SECRET")
    
    # In production, require Turnstile to be configured
    if not secret:
        return bool(app.debug)
    
    # 如果使用测试密钥，直接返回成功（测试模式）
    if secret in ["1x0000000000000000000000000000000AA", "1x00000000000000000000AA"]:
        app.logger.info("Using Turnstile test mode - bypassing verification")
        return True
        
    try:
        data = {"secret": secret, "response": response_token}
        if remote_ip:
            data["remoteip"] = remote_ip
        r = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=data,
            timeout=2,
        )
        j = r.json()
        ok = bool(j.get("success"))
        if not ok:
            # 记录详细错误，便于定位（例如 token 过期、无效、站点密钥不匹配等）
            app.logger.warning(
                "Turnstile failed: ip=%s, codes=%s, body=%s",
                remote_ip,
                j.get("error-codes"),
                j,
            )
        return ok
    except Exception as exc:
        app.logger.warning(f"Turnstile verify error: {exc}")
        # 如果是测试环境且网络请求失败，允许通过
        if app.debug:
            app.logger.info("Debug mode - allowing failed Turnstile verification")
            return True
        return False

# Initialize route blueprints now that all required functions are defined
import routes
blueprints = routes.init_all_routes(
    app, 
    db, 
    model_classes, 
    moderate_content,
    verify_turnstile,
    generate_thumbnails_async,
    send_email_async,
    generate_document_placeholder
)

# Apply CSRF exemptions to all API routes and admin action routes
if 'api' in blueprints:
    # Exempt all API routes from CSRF protection
    for rule in app.url_map.iter_rules():
        if rule.endpoint and rule.endpoint.startswith('api.'):
            view_func = app.view_functions.get(rule.endpoint)
            if view_func:
                csrf.exempt(view_func)

# Exempt admin action routes from CSRF protection
if 'admin' in blueprints:
    for rule in app.url_map.iter_rules():
        if rule.endpoint and 'action' in rule.rule and rule.endpoint.startswith('admin.'):
            view_func = app.view_functions.get(rule.endpoint)
            if view_func:
                csrf.exempt(view_func)
                app.logger.info(f"CSRF exempted: {rule.endpoint}")

# Database initialization flag to prevent double initialization
_db_initialized_flag_key = '_db_initialized_once'

def ensure_db_initialized_once():
    if not getattr(app, _db_initialized_flag_key, False):
        db.create_all()
        ensure_schema_migrations()
        setattr(app, _db_initialized_flag_key, True)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        ensure_schema_migrations()
        
        # 初始化后台任务管理器，传入app实例
        task_manager = get_task_manager(app)
        print("后台任务管理器已初始化")
    
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "9000")), debug=os.getenv("FLASK_DEBUG", "False").lower() == "true")