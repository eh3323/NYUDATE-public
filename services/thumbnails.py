"""
Thumbnail generation service for NYU CLASS Professor Review System

This module contains functions for asynchronous thumbnail generation.
"""

import os
from flask import current_app
from services.file_processing import FileProcessingService


class ThumbnailService:
    """Service for thumbnail generation"""
    
    @staticmethod
    def generate_thumbnails_async(submission_id: int):
        """异步生成所有缩略图"""
        try:
            # Import in function to get the right context
            from flask import current_app
            from app import db, Evidence
            
            # 查找该提交的所有证据
            evidences = Evidence.query.filter_by(submission_id=submission_id).all()
            
            for evidence in evidences:
                try:
                    if evidence.thumbnail_path:
                        continue  # 已有缩略图，跳过
                    
                    if evidence.category in ["image", "chat_image"]:
                        if evidence.file_path and os.path.exists(evidence.file_path):
                            thumbnail_path = FileProcessingService.generate_privacy_thumbnail(
                                evidence.file_path, evidence.id)
                            if thumbnail_path:
                                evidence.thumbnail_path = thumbnail_path
                                current_app.logger.info(f"异步生成缩略图成功: evidence {evidence.id}")
                    
                    elif evidence.category in ["document", "video", "chat_video"]:
                        placeholder_path = FileProcessingService.generate_document_placeholder(
                            evidence.id, 
                            evidence.original_filename, 
                            evidence.description
                        )
                        if placeholder_path:
                            evidence.thumbnail_path = placeholder_path
                            current_app.logger.info(f"异步生成占位符成功: evidence {evidence.id}")
                
                except Exception as e:
                    current_app.logger.error(f"异步处理evidence {evidence.id}失败: {e}")
                    continue
            
            # 提交所有更改
            db.session.commit()
            current_app.logger.info(f"submission {submission_id} 的所有缩略图生成完成")
                
        except Exception as e:
            current_app.logger.error(f"异步生成缩略图失败 submission {submission_id}: {e}")
            try:
                from app import db
                db.session.rollback()
            except:
                pass  # If rollback fails, just log the error above


# Convenience function for backward compatibility
def generate_thumbnails_async(submission_id: int):
    """Convenience function for generating thumbnails asynchronously"""
    return ThumbnailService.generate_thumbnails_async(submission_id)