"""
Services package for NYU CLASS Professor Review System

This package contains business logic services including:
- Content moderation (OpenAI API integration)
- File processing (thumbnails, placeholders)
- Email notifications
- Thumbnail generation
"""

# Make services easily importable
from .moderation import ModerationService, moderate_content, moderate_comment
from .file_processing import FileProcessingService, generate_privacy_thumbnail, generate_document_placeholder
from .email import EmailService, send_email_async
from .thumbnails import ThumbnailService, generate_thumbnails_async

__all__ = [
    'ModerationService',
    'moderate_content', 
    'moderate_comment',
    'FileProcessingService',
    'generate_privacy_thumbnail',
    'generate_document_placeholder',
    'EmailService', 
    'send_email_async',
    'ThumbnailService',
    'generate_thumbnails_async'
]