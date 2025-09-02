#!/usr/bin/env python3
"""
为现有的Evidence记录生成缺失的缩略图
在服务器部署后运行此脚本
"""
import os
from app import app, db, Evidence, generate_privacy_thumbnail, generate_document_placeholder

def generate_missing_thumbnails():
    with app.app_context():
        # 查找没有缩略图的记录
        evidences = Evidence.query.filter(
            (Evidence.thumbnail_path.is_(None)) | 
            (Evidence.thumbnail_path == '')
        ).all()
        
        print(f"找到 {len(evidences)} 个需要生成缩略图的记录")
        
        if not evidences:
            print("所有Evidence记录都已有缩略图")
            return
        
        success_count = 0
        error_count = 0
        
        for ev in evidences:
            try:
                print(f"处理 Evidence ID {ev.id}: {ev.original_filename}")
                
                thumbnail_path = None
                
                # 根据类别生成不同类型的缩略图
                if ev.category in ['image', 'chat_image']:
                    # 图片类型：如果原文件存在，生成模糊缩略图
                    if ev.file_path and os.path.exists(ev.file_path):
                        thumbnail_path = generate_privacy_thumbnail(ev.file_path, ev.id)
                        print(f"  -> 生成图片缩略图")
                    else:
                        # 原文件不存在，生成占位符
                        thumbnail_path = generate_document_placeholder(
                            ev.id, 
                            ev.original_filename, 
                            ev.description or "图片文件"
                        )
                        print(f"  -> 原文件不存在，生成占位符")
                else:
                    # 文档和视频类型：生成现代化占位符
                    thumbnail_path = generate_document_placeholder(
                        ev.id, 
                        ev.original_filename,
                        ev.description or ""
                    )
                    print(f"  -> 生成文档占位符")
                
                if thumbnail_path:
                    ev.thumbnail_path = thumbnail_path
                    success_count += 1
                    print(f"  ✅ 成功: {thumbnail_path}")
                else:
                    error_count += 1
                    print(f"  ❌ 失败: 无法生成缩略图")
                
            except Exception as e:
                error_count += 1
                print(f"  ❌ 错误: {e}")
        
        # 提交更改
        try:
            db.session.commit()
            print(f"\n✅ 处理完成!")
            print(f"成功生成: {success_count} 个缩略图")
            print(f"失败: {error_count} 个记录")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ 数据库提交失败: {e}")

if __name__ == "__main__":
    print("开始为现有Evidence记录生成缩略图...")
    generate_missing_thumbnails()