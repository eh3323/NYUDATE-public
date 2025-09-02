"""
File processing service for NYU CLASS Professor Review System

This module contains functions for file processing, thumbnail generation, and placeholder creation.
"""

import os
import secrets
from PIL import Image, ImageFilter, ImageDraw, ImageFont
from flask import current_app


class FileProcessingService:
    """Service for file processing and thumbnail generation"""
    
    @staticmethod
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
                img.thumbnail(current_app.config['THUMBNAIL_SIZE'], resample_filter)
                
                # Apply blur filter for privacy protection
                blurred_img = img.filter(ImageFilter.GaussianBlur(radius=current_app.config['BLUR_RADIUS']))
                
                # Generate thumbnail filename
                thumbnail_filename = f"thumb_{evidence_id}_{secrets.token_hex(8)}.jpg"
                thumbnail_path = os.path.join(current_app.config['THUMBNAIL_UPLOAD_DIR'], thumbnail_filename)
                
                # Save thumbnail
                blurred_img.save(thumbnail_path, 'JPEG', quality=current_app.config['THUMBNAIL_QUALITY'])
                
                return thumbnail_path
                
        except Exception as e:
            current_app.logger.error(f"Failed to generate thumbnail for {image_path}: {e}")
            return None
    
    @staticmethod
    def generate_document_placeholder(evidence_id: int, filename: str, description: str = None) -> str:
        """Generate a modern placeholder image for document evidence"""
        try:
            # Create a modern gradient background
            img = Image.new('RGB', current_app.config['THUMBNAIL_SIZE'], color='#F8FAFC')
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
            font_medium = None
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
            
            # Generate placeholder filename
            placeholder_filename = f"doc_placeholder_{evidence_id}_{secrets.token_hex(8)}.jpg"
            placeholder_path = os.path.join(current_app.config['THUMBNAIL_UPLOAD_DIR'], placeholder_filename)
            
            # Save clear placeholder (no blur)
            img.save(placeholder_path, 'JPEG', quality=current_app.config['THUMBNAIL_QUALITY'])
            
            return placeholder_path
            
        except Exception as e:
            current_app.logger.error(f"Failed to generate document placeholder: {e}")
            return None
    
    @staticmethod
    def create_sample_image(evidence_id: int, filename: str) -> str:
        """Create a sample image for demo purposes"""
        try:
            # Create a colorful sample image
            img = Image.new('RGB', current_app.config['THUMBNAIL_SIZE'], color='#E0F2FE')
            draw = ImageDraw.Draw(img)
            
            # Create a gradient background
            for y in range(img.height):
                alpha = y / img.height
                color = (
                    int(224 + alpha * (99 - 224)),   # E0F2FE -> 63E6BE gradient
                    int(242 + alpha * (230 - 242)),  
                    int(254 + alpha * (190 - 254))
                )
                draw.line([(0, y), (img.width, y)], fill=color)
            
            # Draw sample content
            center_x, center_y = img.width // 2, img.height // 2
            
            # Draw a decorative circle
            circle_radius = 40
            draw.ellipse([center_x - circle_radius, center_y - circle_radius - 20, 
                         center_x + circle_radius, center_y + circle_radius - 20], 
                        fill='#FFFFFF', outline='#22D3EE', width=3)
            
            # Try to load font for text
            font = None
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 14)
            except:
                font = ImageFont.load_default()
            
            # Add sample text
            sample_text = "SAMPLE"
            if font:
                bbox = draw.textbbox((0, 0), sample_text, font=font)
                text_width = bbox[2] - bbox[0]
                text_x = center_x - text_width // 2
                draw.text((text_x, center_y - 25), sample_text, fill='#0891B2', font=font)
            
            # Add filename below
            display_filename = filename[:15] + "..." if len(filename) > 15 else filename
            if font:
                bbox = draw.textbbox((0, 0), display_filename, font=font)
                text_width = bbox[2] - bbox[0]
                text_x = center_x - text_width // 2
                draw.text((text_x, center_y + 30), display_filename, fill='#0F172A', font=font)
            
            # Generate sample filename
            sample_filename = f"sample_{evidence_id}_{secrets.token_hex(8)}.jpg"
            sample_path = os.path.join(current_app.config['THUMBNAIL_UPLOAD_DIR'], sample_filename)
            
            # Save sample image
            img.save(sample_path, 'JPEG', quality=current_app.config['THUMBNAIL_QUALITY'])
            
            return sample_path
            
        except Exception as e:
            current_app.logger.error(f"Failed to create sample image: {e}")
            return None


# Convenience functions for backward compatibility
def generate_privacy_thumbnail(image_path: str, evidence_id: int) -> str:
    """Convenience function for generating privacy thumbnail"""
    return FileProcessingService.generate_privacy_thumbnail(image_path, evidence_id)


def generate_document_placeholder(evidence_id: int, filename: str, description: str = None) -> str:
    """Convenience function for generating document placeholder"""
    return FileProcessingService.generate_document_placeholder(evidence_id, filename, description)


def create_sample_image(evidence_id: int, filename: str) -> str:
    """Convenience function for creating sample image"""
    return FileProcessingService.create_sample_image(evidence_id, filename)