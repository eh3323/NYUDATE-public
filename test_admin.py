#!/usr/bin/env python3

# 测试脚本：检查87号提交能否成功审批

from app import app, db, Submission, ReviewStatus

def test_approve_87():
    with app.app_context():
        # 查找87号提交
        sub = db.session.get(Submission, 87)
        if not sub:
            print("❌ Submission 87 not found")
            return False
            
        print(f"✅ Found submission 87: {sub.professor_cn_name}, status: {sub.status}")
        
        # 尝试手动审批
        original_status = sub.status
        sub.status = ReviewStatus.APPROVED
        
        try:
            db.session.commit()
            print("✅ Database commit successful")
            
            # 验证状态
            sub_check = db.session.get(Submission, 87)
            if sub_check.status == ReviewStatus.APPROVED:
                print("✅ Status verification passed - submission approved")
                return True
            else:
                print(f"❌ Status verification failed: expected approved, got {sub_check.status}")
                return False
                
        except Exception as e:
            print(f"❌ Database commit failed: {e}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    result = test_approve_87()
    print(f"\n🎯 Test result: {'SUCCESS' if result else 'FAILED'}")