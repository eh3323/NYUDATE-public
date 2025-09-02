#!/usr/bin/env python3
"""
安全性测试脚本
验证修复后的安全机制是否正常工作
"""

import os
import sys
import time
from datetime import datetime

# 添加当前目录到Python路径以便导入app模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_rate_limiter():
    """测试自定义Rate Limiter"""
    print("=== 测试Rate Limiter ===")
    
    from app import RateLimiter
    
    # 创建测试用的rate limiter
    limiter = RateLimiter()
    test_ip = "192.168.1.100"
    
    # 测试正常请求
    print(f"测试IP {test_ip} 的正常请求...")
    
    success_count = 0
    for i in range(15):  # 测试15次请求，限制是10次
        if limiter.is_allowed(test_ip, limit=10, window=60):
            success_count += 1
            print(f"请求 {i+1}: 通过")
        else:
            print(f"请求 {i+1}: 被阻止 (累计成功: {success_count})")
            break
    
    print(f"总共成功请求: {success_count}/15")
    
    # 测试剩余次数计算
    remaining = limiter.get_remaining_attempts(test_ip, limit=10, window=60)
    print(f"剩余请求次数: {remaining}")
    
    print("Rate Limiter测试完成\n")

def test_privacy_parameter_validation():
    """测试隐私参数验证逻辑"""
    print("=== 测试隐私参数验证 ===")
    
    # 模拟不同的from_privacy参数值
    test_cases = ['0', '1', '2', 'true', 'false', 'malicious_value', '']
    
    valid_values = ['0', '1']
    
    for test_value in test_cases:
        is_valid = test_value in valid_values
        print(f"参数值 '{test_value}': {'有效' if is_valid else '无效'}")
    
    print("隐私参数验证测试完成\n")

def test_logging_functionality():
    """测试日志记录功能"""
    print("=== 测试日志记录功能 ===")
    
    import logging
    from app import app
    
    # 配置测试日志
    logging.basicConfig(level=logging.INFO)
    
    with app.app_context():
        app.logger.info("测试日志记录: 正常访问记录")
        app.logger.warning("测试日志记录: 可疑访问尝试")
        
    print("日志记录功能测试完成\n")

def test_security_headers():
    """测试安全响应头"""
    print("=== 测试安全响应头 ===")
    
    from app import app
    
    with app.test_client() as client:
        # 测试首页的安全头
        response = client.get('/')
        
        print("响应头检查:")
        security_headers = [
            'Content-Security-Policy',
            'X-Frame-Options', 
            'X-Content-Type-Options',
            'Strict-Transport-Security'
        ]
        
        for header in security_headers:
            if header in response.headers:
                print(f"✓ {header}: {response.headers[header][:50]}...")
            else:
                print(f"✗ {header}: 缺失")
    
    print("安全响应头测试完成\n")

def main():
    """主测试函数"""
    print("开始安全性测试...")
    print(f"测试时间: {datetime.now()}")
    print("=" * 50)
    
    try:
        test_rate_limiter()
        test_privacy_parameter_validation()
        test_logging_functionality()
        test_security_headers()
        
        print("=" * 50)
        print("所有安全性测试完成!")
        
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()