import os
import magic
import secrets
import json
from datetime import datetime
import typing
from PIL import Image, ImageFilter, ImageDraw, ImageFont
from background_tasks import get_task_manager
import openai

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect, generate_csrf
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import text
import requests

from config import Config

# Import utility functions from utils package
from utils.security import RateLimiter, clean_expired_sessions
from utils.email_sender import send_html_email

# Import services
from services.moderation import moderate_content, moderate_comment
from services.file_processing import generate_privacy_thumbnail, generate_document_placeholder
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

# Inject globals into templates
@app.context_processor
def inject_globals():
    return {
        "config": app.config,
        # Expose a real CSRF token generator for templates
        "csrf_token": generate_csrf,
    }


# Initialize security extensions
csrf = CSRFProtect(app)

# API routes will be exempted below using decorator

# Configure Talisman with relaxed CSP for inline styles and fonts
csp = {
    'default-src': "'self'",
    'style-src': "'self' 'unsafe-inline' fonts.googleapis.com",
    'font-src': "'self' fonts.gstatic.com",
    'script-src': "'self' 'unsafe-inline' challenges.cloudflare.com",
    'img-src': "'self' data:",
    'connect-src': "'self' challenges.cloudflare.com",
    'frame-src': "'self' challenges.cloudflare.com",
}
talisman = Talisman(app, force_https=app.config.get("FORCE_HTTPS", False), content_security_policy=csp)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["10000 per day", "5000 per hour"],
    storage_uri=app.config.get("RATELIMIT_STORAGE_URI", "memory://")
)
limiter.init_app(app)

db = SQLAlchemy(app)
mail = Mail(app)

# Initialize custom rate limiter and make it available to the app
app.rate_limiter = RateLimiter()
app.mail = mail  # Make mail available to utils modules

# Initialize models
import models
model_classes = models.init_models(db)
# Import model classes for use in routes
ReviewStatus = model_classes['ReviewStatus']
Submission = model_classes['Submission'] 
Evidence = model_classes['Evidence']
Appeal = model_classes['Appeal']
AppealEvidence = model_classes['AppealEvidence']
Like = model_classes['Like']
Comment = model_classes['Comment']
mask_name = model_classes['mask_name']

# Initialize route blueprints (will be done after all functions are defined)
import routes



# Create upload dirs if not present
for _dir in [
    app.config["BASE_UPLOAD_DIR"],
    app.config["IMAGE_UPLOAD_DIR"],
    app.config["DOC_UPLOAD_DIR"],
    app.config["VIDEO_UPLOAD_DIR"],
    app.config["THUMBNAIL_UPLOAD_DIR"],
]:
    os.makedirs(_dir, exist_ok=True)



# Session cleanup will be handled by the utils.security module via before_request hook

@app.before_request
def before_request_cleanup():
    """每个请求前清理过期的session"""
    clean_expired_sessions()









# moderate_content function moved to services/moderation.py


# Will initialize route blueprints after all functions are defined


# moderate_comment function moved to services/moderation.py

# generate_privacy_thumbnail function moved to services/file_processing.py
    """
    使用OpenAI API对评论内容进行审核
    返回审核结果字典
    """
    try:
        # 检查是否启用内容审核
        if not app.config.get('CONTENT_MODERATION_ENABLED', True):
            return {
                'action': 'ALLOW',
                'reasons': ['Content moderation disabled'],
                'client_notice': ''
            }
        
        # 检查API密钥配置
        api_key = app.config.get('OPENAI_API_KEY')
        if not api_key:
            app.logger.warning("OpenAI API key not configured, skipping comment moderation")
            return {
                'action': 'ALLOW',
                'reasons': ['API key not configured'],
                'client_notice': ''
            }
        
        # 读取评论审核的prompt和schema文件
        try:
            prompt_path = os.path.join(os.path.dirname(__file__), 'Comment Prompt.txt')
            schema_path = os.path.join(os.path.dirname(__file__), 'comment schema.json')
            
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_content = f.read()
            
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_content = json.loads(f.read())
                
        except Exception as e:
            app.logger.error(f"Failed to read comment prompt or schema files: {e}")
            return {
                'action': 'ALLOW',
                'reasons': ['Config file error'],
                'client_notice': ''
            }
        
        # 设置OpenAI客户端
        if app.config.get('OPENAI_BASE_URL'):
            client = openai.OpenAI(api_key=api_key, base_url=app.config.get('OPENAI_BASE_URL'))
        else:
            client = openai.OpenAI(api_key=api_key)
        
        # 检查SDK版本
        def _parse_ver(v: str) -> tuple:
            parts = v.split(".")
            try:
                return tuple(int(x) for x in parts[:3])
            except Exception:
                return (0, 0, 0)

        ver = str(getattr(openai, "__version__", "0.0.0")).split("+")[0]
        use_responses = _parse_ver(ver) >= (1, 55, 0)

        result = None
        response = None

        try:
            if not use_responses:
                app.logger.error("OpenAI SDK too old for Responses API: %s (require >= 1.55)", ver)
                return {
                    'action': 'ALLOW',
                    'reasons': ['OpenAI SDK too old (need >= 1.55)'],
                    'client_notice': ''
                }

            app.logger.info("Calling OpenAI Responses API for comment moderation... model=%s", app.config.get('OPENAI_MODEL', 'gpt-5'))
            response = client.responses.create(
                model=app.config.get('OPENAI_MODEL', 'gpt-5'),
                input=f"{prompt_content}\n\n用户内容：\n{content}",
                reasoning={'effort': 'minimal'},
                text={
                    'verbosity': 'low',
                    'format': {
                        'type': 'json_schema',
                        'name': schema_content.get('name', 'CommentPIIModeration'),
                        'schema': schema_content.get('schema', {}),
                        'strict': bool(schema_content.get('strict', False)),
                    },
                },
                timeout=app.config.get('OPENAI_API_TIMEOUT', 30),
            )
            
            # 解析响应
            try:
                output_text = getattr(response, 'output_text', None)
                if output_text:
                    result = json.loads(output_text)
            except Exception:
                result = None
            
            if result is None:
                try:
                    output = getattr(response, 'output', None)
                    if output:
                        for item in output:
                            contents = getattr(item, 'content', [])
                            for content_item in contents:
                                content_json = getattr(content_item, 'json', None)
                                if content_json is not None:
                                    result = content_json
                                    break
                            if result is not None:
                                break
                except Exception:
                    result = None
        except Exception as e:
            app.logger.error(f"OpenAI Responses API error for comment: {e}")
            result = None

        if result is None:
            raise json.JSONDecodeError("No JSON output found", doc=str(response) if response is not None else "", pos=0)
        
        # 记录审核日志
        app.logger.info(f"Comment moderation result: {result.get('action', 'UNKNOWN')}")
        
        # 确保client_notice字段存在且为有效字符串
        if 'client_notice' not in result:
            result['client_notice'] = ''
        elif result['client_notice'] is None:
            result['client_notice'] = ''
        elif not isinstance(result['client_notice'], str):
            result['client_notice'] = str(result['client_notice'])
        
        # 如果是FLAG_AND_FIX但client_notice为空，提供默认消息
        if result.get('action') == 'FLAG_AND_FIX' and not result['client_notice'].strip():
            result['client_notice'] = '评论内容需要修改，请修改后重新提交'
        
        return result
        
    except openai.APITimeoutError:
        app.logger.error("OpenAI API timeout for comment")
        return {
            'action': 'ALLOW',
            'reasons': ['API timeout'],
            'client_notice': ''
        }
    except openai.APIError as e:
        app.logger.error(f"OpenAI API error for comment: {e}")
        return {
            'action': 'ALLOW', 
            'reasons': ['API error'],
            'client_notice': ''
        }
    except json.JSONDecodeError as e:
        app.logger.error(f"Failed to parse OpenAI response for comment: {e}")
        return {
            'action': 'ALLOW',
            'reasons': ['Response parse error'], 
            'client_notice': ''
        }
    except Exception as e:
        app.logger.error(f"Unexpected error in comment moderation: {e}")
        return {
            'action': 'ALLOW',
            'reasons': ['Unexpected error'],
            'client_notice': ''
        }



# generate_thumbnails_async function moved to services/thumbnails.py
    """Generate a blurred thumbnail for privacy protection"""
    try:
        # Open the original image
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Calculate thumbnail size while maintaining aspect ratio
            # Pillow compatibility: fallback if Image.Resampling is unavailable
            try:
                resample_filter = Image.Resampling.LANCZOS  # Pillow >= 9.1
            except AttributeError:
                # Older Pillow versions
                resample_filter = getattr(Image, 'LANCZOS', getattr(Image, 'ANTIALIAS', Image.BICUBIC))
            img.thumbnail(app.config['THUMBNAIL_SIZE'], resample_filter)
            
            # Apply blur filter for privacy protection
            blurred_img = img.filter(ImageFilter.GaussianBlur(radius=app.config['BLUR_RADIUS']))
            
            # Generate thumbnail filename
            thumbnail_filename = f"thumb_{evidence_id}_{secrets.token_hex(8)}.jpg"
            thumbnail_path = os.path.join(app.config['THUMBNAIL_UPLOAD_DIR'], thumbnail_filename)
            
            # Save thumbnail
            blurred_img.save(thumbnail_path, 'JPEG', quality=app.config['THUMBNAIL_QUALITY'])
            
            return thumbnail_path
            
    except Exception as e:
        app.logger.error(f"Failed to generate thumbnail for {image_path}: {e}")
        return None


# send_email_async function moved to services/email.py
    """异步生成所有缩略图"""
    try:
        with app.app_context():
            # 查找该提交的所有证据
            evidences = Evidence.query.filter_by(submission_id=submission_id).all()
            
            for evidence in evidences:
                try:
                    if evidence.thumbnail_path:
                        continue  # 已有缩略图，跳过
                    
                    if evidence.category in ["image", "chat_image"]:
                        if evidence.file_path and os.path.exists(evidence.file_path):
                            thumbnail_path = generate_privacy_thumbnail(evidence.file_path, evidence.id)
                            if thumbnail_path:
                                evidence.thumbnail_path = thumbnail_path
                                app.logger.info(f"异步生成缩略图成功: evidence {evidence.id}")
                    
                    elif evidence.category in ["document", "video", "chat_video"]:
                        placeholder_path = generate_document_placeholder(
                            evidence.id, 
                            evidence.original_filename, 
                            evidence.description
                        )
                        if placeholder_path:
                            evidence.thumbnail_path = placeholder_path
                            app.logger.info(f"异步生成占位符成功: evidence {evidence.id}")
                
                except Exception as e:
                    app.logger.error(f"异步处理evidence {evidence.id}失败: {e}")
                    continue
            
            # 提交所有更改
            db.session.commit()
            app.logger.info(f"submission {submission_id} 的所有缩略图生成完成")
            
    except Exception as e:
        app.logger.error(f"异步生成缩略图失败 submission {submission_id}: {e}")
        db.session.rollback()


# generate_document_placeholder function moved to services/file_processing.py
    """异步发送邮件"""
    try:
        with app.app_context():
            send_html_email(**email_data)
            app.logger.info(f"异步邮件发送成功: {email_data.get('recipients', 'unknown')}")
    except Exception as e:
        app.logger.error(f"异步邮件发送失败: {e}")


# create_sample_image function moved to services/file_processing.py
    """Generate a modern placeholder image for document evidence"""
    try:
        # Create a modern gradient background
        img = Image.new('RGB', app.config['THUMBNAIL_SIZE'], color='#F8FAFC')
        draw = ImageDraw.Draw(img)
        
        # Create subtle gradient background
        for y in range(img.height):
            alpha = y / img.height
            color = (
                int(248 + alpha * (241 - 248)),  # F8F8F8 -> F1F5F9
                int(250 + alpha * (245 - 250)),  
                int(252 + alpha * (249 - 252))
            )
            draw.line([(0, y), (img.width, y)], fill=color)
        
        # Modern document container
        container_width, container_height = 120, 140
        x = (img.width - container_width) // 2
        y = (img.height - container_height) // 2 - 10
        
        # Document shadow (subtle)
        shadow_offset = 4
        draw.rounded_rectangle([x + shadow_offset, y + shadow_offset, 
                               x + container_width + shadow_offset, y + container_height + shadow_offset], 
                              radius=8, fill='#E2E8F0', outline=None)
        
        # Main document container with rounded corners
        draw.rounded_rectangle([x, y, x + container_width, y + container_height], 
                              radius=8, fill='#FFFFFF', outline='#CBD5E1', width=1)
        
        # Modern document header (mimicking PDF header)
        header_height = 25
        draw.rounded_rectangle([x + 1, y + 1, x + container_width - 1, y + header_height], 
                              radius=7, fill='#3B82F6', outline=None)
        
        # PDF icon area in header
        icon_size = 16
        icon_x = x + 8
        icon_y = y + (header_height - icon_size) // 2
        draw.rounded_rectangle([icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
                              radius=2, fill='#FFFFFF', outline=None)
        
        # Document content lines with modern spacing
        content_start_y = y + header_height + 15
        line_spacing = 12
        lines = [
            (container_width * 0.8, '#64748B'),   # Full line
            (container_width * 0.6, '#94A3B8'),   # Medium line  
            (container_width * 0.9, '#64748B'),   # Full line
            (container_width * 0.4, '#94A3B8'),   # Short line
            (container_width * 0.7, '#94A3B8'),   # Medium line
        ]
        
        for i, (line_width, color) in enumerate(lines):
            if content_start_y + i * line_spacing + 3 < y + container_height - 10:
                draw.rounded_rectangle([x + 12, content_start_y + i * line_spacing, 
                                       x + 12 + line_width, content_start_y + i * line_spacing + 3],
                                      radius=1, fill=color, outline=None)
        
        # Try to load modern font
        try:
            font_medium = ImageFont.truetype("/System/Library/Fonts/SF-Pro-Display-Medium.otf", 12)
        except:
            try:
                font_medium = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 12)
            except:
                font_medium = ImageFont.load_default()
        
        # File type indicator
        file_ext = filename.split('.')[-1].upper() if '.' in filename else 'DOC'
        if font_medium:
            ext_text = file_ext[:4]  # Limit to 4 chars
            bbox = draw.textbbox((0, 0), ext_text, font=font_medium)
            text_width = bbox[2] - bbox[0]
            ext_x = x + container_width - text_width - 8
            ext_y = icon_y + 1
            draw.text((ext_x, ext_y), ext_text, fill='#FFFFFF', font=font_medium)
        
        # Description below container with modern typography (fallback to filename if no description)
        display_text = description[:30] + "..." if description and len(description) > 30 else description
        if not display_text:  # Fallback to filename if no description
            display_text = filename[:20] + "..." if len(filename) > 20 else filename
            
        if font_medium and display_text:
            bbox = draw.textbbox((0, 0), display_text, font=font_medium)
            text_width = bbox[2] - bbox[0]
            text_x = (img.width - text_width) // 2
            draw.text((text_x, y + container_height + 15), display_text, 
                     fill='#475569', font=font_medium)
        
        # 文档图标不需要模糊化处理，保持清晰可读
        # 不再应用模糊效果，直接保存清晰的占位符
        
        # Generate placeholder filename
        placeholder_filename = f"doc_placeholder_{evidence_id}_{secrets.token_hex(8)}.jpg"
        placeholder_path = os.path.join(app.config['THUMBNAIL_UPLOAD_DIR'], placeholder_filename)
        
        # Save clear placeholder (no blur)
        img.save(placeholder_path, 'JPEG', quality=app.config['THUMBNAIL_QUALITY'])
        
        return placeholder_path
        
    except Exception as e:
        app.logger.error(f"Failed to generate document placeholder: {e}")
        return None


    """Create a sample image for demo purposes"""
    try:
        # Create a colorful sample image
        img = Image.new('RGB', app.config['THUMBNAIL_SIZE'], color='#E0F2FE')
        draw = ImageDraw.Draw(img)
        
        # Create a gradient background
        for y in range(img.height):
            alpha = y / img.height
            color = (
                int(224 + alpha * (59 - 224)),   # E0 -> 3B
                int(242 + alpha * (130 - 242)),  # F2 -> 82
                int(254 + alpha * (246 - 254))   # FE -> F6
            )
            draw.line([(0, y), (img.width, y)], fill=color)
        
        # Add some sample content shapes
        import random
        random.seed(evidence_id)  # Consistent randomness based on ID
        
        # Draw some rectangles and circles to simulate content
        for i in range(5):
            x1 = random.randint(20, img.width//2)
            y1 = random.randint(20, img.height//2)
            x2 = x1 + random.randint(40, 100)
            y2 = y1 + random.randint(20, 60)
            
            color = (
                random.randint(100, 200),
                random.randint(100, 200), 
                random.randint(100, 200)
            )
            
            if i % 2 == 0:
                draw.rectangle([x1, y1, x2, y2], fill=color, outline=None)
            else:
                draw.ellipse([x1, y1, x2, y2], fill=color, outline=None)
        
        # Add some text to simulate content
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 14)
        except:
            font = ImageFont.load_default()
            
        if font:
            sample_texts = ["Sample Evidence", "Chat Screenshot", "Document Scan", "Photo Evidence"]
            text = random.choice(sample_texts)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_x = (img.width - text_width) // 2
            draw.text((text_x, img.height - 40), text, fill='#1F2937', font=font)
        
        # Save sample image
        os.makedirs(app.config['IMAGE_UPLOAD_DIR'], exist_ok=True)
        sample_filename = f"sample_{evidence_id}_{secrets.token_hex(8)}.jpg"
        sample_path = os.path.join(app.config['IMAGE_UPLOAD_DIR'], sample_filename)
        img.save(sample_path, 'JPEG', quality=85)
        
        return sample_path
        
    except Exception as e:
        app.logger.error(f"Failed to create sample image: {e}")
        return None


def ensure_schema_migrations():
    # PostgreSQL schema migration
    with db.engine.begin() as conn:
            conn.execute(text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='submissions' AND column_name='privacy_homepage'
                    ) THEN
                        ALTER TABLE submissions ADD COLUMN privacy_homepage BOOLEAN NOT NULL DEFAULT FALSE;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='submissions' AND column_name='professor_birthday'
                    ) THEN
                        ALTER TABLE submissions ADD COLUMN professor_birthday VARCHAR(32) NULL;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='evidences' AND column_name='thumbnail_path'
                    ) THEN
                        ALTER TABLE evidences ADD COLUMN thumbnail_path VARCHAR(1024) NULL;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='evidences' AND column_name='description'
                    ) THEN
                        ALTER TABLE evidences ADD COLUMN description TEXT NULL;
                    END IF;
                    -- 添加新的褒义标签字段
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

# Apply CSRF exemptions to all API routes
if 'api' in blueprints:
    # Exempt all API routes from CSRF protection
    for rule in app.url_map.iter_rules():
        if rule.endpoint and rule.endpoint.startswith('api.'):
            view_func = app.view_functions.get(rule.endpoint)
            if view_func:
                csrf.exempt(view_func)



































if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        ensure_schema_migrations()
        
        # 初始化后台任务管理器
        task_manager = get_task_manager()
        print("后台任务管理器已初始化")
    
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "9000")), debug=os.getenv("FLASK_DEBUG", "False").lower() == "true")

# Ensure correct proxy handling and one-time DB initialization when running behind a reverse proxy (e.g., Nginx/Cloudflare)
if app.config.get("BEHIND_PROXY", False):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

_db_initialized_flag_key = "_db_initialized_once"

@app.before_request
def ensure_db_initialized_once():
    if not getattr(app, _db_initialized_flag_key, False):
        try:
            with app.app_context():
                db.create_all()
                ensure_schema_migrations()
                
                # 初始化后台任务管理器
                task_manager = get_task_manager()
                app.logger.info("后台任务管理器已初始化")
        finally:
            setattr(app, _db_initialized_flag_key, True)
