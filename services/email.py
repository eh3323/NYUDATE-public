"""
Email service for NYU CLASS Professor Review System

This module contains functions for sending emails asynchronously.
"""

from flask import current_app
from utils.email_sender import send_html_email


class EmailService:
    """Service for email sending"""
    
    @staticmethod
    def send_email_async(email_data: dict):
        """异步发送邮件"""
        try:
            with current_app.app_context():
                send_html_email(**email_data)
                current_app.logger.info(f"异步邮件发送成功: {email_data.get('recipients', 'unknown')}")
        except Exception as e:
            current_app.logger.error(f"异步邮件发送失败: {e}")


# Convenience function for backward compatibility
def send_email_async(email_data: dict):
    """Convenience function for sending email asynchronously"""
    return EmailService.send_email_async(email_data)