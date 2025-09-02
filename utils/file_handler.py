"""
File handling utilities for NYU Dating Copilot

This module contains functions for file validation, image processing,
and thumbnail generation.
"""

import os
import secrets
from PIL import Image, ImageFilter
from flask import current_app as app


def allowed_file(filename: str, allowed_extensions: set[str]) -> bool:
    """Check if a filename has an allowed extension"""
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in allowed_extensions


def generate_privacy_thumbnail(image_path: str, evidence_id: int) -> str:
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