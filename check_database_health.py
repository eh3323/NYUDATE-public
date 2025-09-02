#!/usr/bin/env python3
"""
检查数据库健康状态和新字段
部署后运行此脚本验证migration是否成功
"""
from app import app, db, Submission, Evidence
from sqlalchemy import text

def check_database_health():
    with app.app_context():
        print("🔍 检查数据库连接和schema状态...\n")
        
        try:
            # 检查数据库连接
            db.session.execute(text("SELECT 1"))
            print("✅ 数据库连接正常")
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            return
        
        # 检查submissions表的新字段
        print("\n📊 检查submissions表字段:")
        try:
            result = db.session.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'submissions'
                AND column_name IN ('tag_loyal', 'tag_stable', 'tag_sincere', 'tag_humorous', 'privacy_homepage', 'professor_birthday')
                ORDER BY column_name
            """))
            
            expected_fields = ['tag_loyal', 'tag_stable', 'tag_sincere', 'tag_humorous', 'privacy_homepage', 'professor_birthday']
            found_fields = []
            
            for row in result:
                found_fields.append(row[0])
                print(f"  ✅ {row[0]}: {row[1]} (nullable: {row[2]}, default: {row[3]})")
            
            missing_fields = set(expected_fields) - set(found_fields)
            if missing_fields:
                print(f"  ❌ 缺失字段: {missing_fields}")
            else:
                print("  🎉 所有预期字段都存在!")
                
        except Exception as e:
            print(f"  ❌ 检查submissions字段失败: {e}")
        
        # 检查evidences表的新字段
        print("\n📁 检查evidences表字段:")
        try:
            result = db.session.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'evidences'
                AND column_name IN ('thumbnail_path', 'description')
                ORDER BY column_name
            """))
            
            expected_fields = ['thumbnail_path', 'description']
            found_fields = []
            
            for row in result:
                found_fields.append(row[0])
                print(f"  ✅ {row[0]}: {row[1]} (nullable: {row[2]})")
            
            missing_fields = set(expected_fields) - set(found_fields)
            if missing_fields:
                print(f"  ❌ 缺失字段: {missing_fields}")
            else:
                print("  🎉 所有预期字段都存在!")
                
        except Exception as e:
            print(f"  ❌ 检查evidences字段失败: {e}")
        
        # 检查数据统计
        print("\n📈 数据统计:")
        try:
            total_submissions = Submission.query.count()
            total_evidences = Evidence.query.count()
            evidences_with_thumbnails = Evidence.query.filter(Evidence.thumbnail_path.isnot(None)).count()
            evidences_with_descriptions = Evidence.query.filter(Evidence.description.isnot(None)).count()
            
            # 检查新标签的使用情况
            positive_tags_count = Submission.query.filter(
                (Submission.tag_loyal == True) |
                (Submission.tag_stable == True) |
                (Submission.tag_sincere == True) |
                (Submission.tag_humorous == True)
            ).count()
            
            print(f"  📝 总提交数: {total_submissions}")
            print(f"  📎 总证据数: {total_evidences}")
            print(f"  🖼️  有缩略图的证据: {evidences_with_thumbnails}/{total_evidences}")
            print(f"  📄 有描述的证据: {evidences_with_descriptions}/{total_evidences}")
            print(f"  ✨ 使用新正面标签的提交: {positive_tags_count}/{total_submissions}")
            
            if evidences_with_thumbnails < total_evidences:
                print(f"  ⚠️  有 {total_evidences - evidences_with_thumbnails} 个证据缺少缩略图")
                print("     建议运行: python3 generate_missing_thumbnails.py")
            
        except Exception as e:
            print(f"  ❌ 获取统计数据失败: {e}")
        
        print(f"\n🏁 数据库健康检查完成!")

if __name__ == "__main__":
    check_database_health()