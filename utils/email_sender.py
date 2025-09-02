"""
Email sending utilities for NYU Dating Copilot

This module contains functions for sending HTML emails,
admin notifications, and other email-related functionality.
"""

from flask import render_template, request, has_request_context, current_app as app
from flask_mail import Message


def send_html_email(subject, recipients, email_title, email_content, details=None, button_text=None, button_url=None, sender=None):
    """发送HTML格式邮件的统一函数"""
    try:
        # Import mail from app context to avoid circular imports
        from flask import current_app
        mail = current_app.mail
        
        if not app.config.get("MAIL_SERVER"):
            app.logger.info("邮件服务未配置，跳过发送")
            return False
            
        # 安全地获取base_url，处理没有请求上下文的情况
        try:
            if has_request_context() and request:
                base_url = request.host_url
            else:
                base_url = app.config.get('BASE_URL', 'https://nyudate.icloud.com')
        except:
            base_url = app.config.get('BASE_URL', 'https://nyudate.icloud.com')
        
        # 渲染HTML模板
        html_content = render_template('email_template.html',
            subject=subject,
            email_title=email_title,
            email_content=email_content,
            details=details,
            button_text=button_text,
            button_url=button_url,
            base_url=base_url
        )
        
        # 创建纯文本版本（简化版）
        text_content = f"{email_title}\n\n{email_content}"
        if details:
            text_content += f"\n\n详细信息：\n{details}"
        if button_url:
            text_content += f"\n\n{button_text or '查看详情'}：{button_url}"
        text_content += "\n\n---\nNYU Dating Copilot\n本邮件由系统自动发送，请勿回复。"
        
        # 创建邮件消息
        msg = Message(
            subject=subject,
            recipients=recipients if isinstance(recipients, list) else [recipients],
            sender=sender or app.config.get("MAIL_DEFAULT_SENDER") or app.config.get("MAIL_USERNAME"),
            html=html_content,
            body=text_content
        )
        
        mail.send(msg)
        app.logger.info(f"邮件发送成功: {subject} -> {recipients}")
        return True
        
    except Exception as e:
        app.logger.warning(f"发送邮件失败: {e}")
        return False


def send_admin_notification(subject, content):
    """发送简单的管理员通知邮件"""
    try:
        # Import mail from app context to avoid circular imports
        from flask import current_app
        mail = current_app.mail
        
        if not app.config.get("MAIL_SERVER"):
            app.logger.info("邮件服务未配置，跳过通知")
            return False
            
        admin_email = app.config.get("MAIL_USERNAME")  # 发送给管理员邮箱
        
        msg = Message(
            subject=f"NYU Date - {subject}",
            recipients=[admin_email],
            sender=app.config.get("MAIL_DEFAULT_SENDER") or admin_email,
            body=content
        )
        
        mail.send(msg)
        app.logger.info(f"管理员通知发送成功: {subject}")
        return True
        
    except Exception as e:
        app.logger.warning(f"发送管理员通知失败: {e}")
        return False