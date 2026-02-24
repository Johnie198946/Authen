#!/usr/bin/env python3
"""
简单的OpenID Connect实现验证脚本
不需要完整的测试环境，只验证代码逻辑
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.utils.jwt import create_id_token, decode_token
from datetime import datetime

def verify_id_token_function():
    """验证ID Token生成函数"""
    print("=" * 60)
    print("验证ID Token生成函数")
    print("=" * 60)
    
    # 测试数据
    user_data = {
        "sub": "test-user-123",
        "name": "Test User",
        "email": "test@example.com",
        "email_verified": True,
        "preferred_username": "testuser"
    }
    client_id = "test_client"
    
    try:
        # 生成ID Token
        id_token = create_id_token(user_data, client_id)
        print(f"✓ ID Token生成成功")
        print(f"  Token长度: {len(id_token)}")
        
        # 解码ID Token
        payload = decode_token(id_token)
        if payload is None:
            print("✗ ID Token解码失败")
            return False
        
        print(f"✓ ID Token解码成功")
        
        # 验证必需的OpenID Connect声明
        required_claims = ["iss", "sub", "aud", "exp", "iat"]
        for claim in required_claims:
            if claim not in payload:
                print(f"✗ 缺少必需的声明: {claim}")
                return False
        print(f"✓ 包含所有必需的OpenID Connect声明")
        
        # 验证用户信息
        if payload["sub"] != user_data["sub"]:
            print(f"✗ sub不匹配: {payload['sub']} != {user_data['sub']}")
            return False
        print(f"✓ sub正确: {payload['sub']}")
        
        if payload["name"] != user_data["name"]:
            print(f"✗ name不匹配: {payload['name']} != {user_data['name']}")
            return False
        print(f"✓ name正确: {payload['name']}")
        
        if payload["email"] != user_data["email"]:
            print(f"✗ email不匹配: {payload['email']} != {user_data['email']}")
            return False
        print(f"✓ email正确: {payload['email']}")
        
        if payload["aud"] != client_id:
            print(f"✗ aud不匹配: {payload['aud']} != {client_id}")
            return False
        print(f"✓ aud正确: {payload['aud']}")
        
        # 验证时间戳
        if payload["exp"] <= payload["iat"]:
            print(f"✗ 过期时间应该大于签发时间")
            return False
        print(f"✓ 时间戳正确 (exp > iat)")
        
        print("\n" + "=" * 60)
        print("✓ ID Token生成函数验证通过")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"✗ 验证失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def verify_sso_service_code():
    """验证SSO服务代码结构"""
    print("\n" + "=" * 60)
    print("验证SSO服务代码结构")
    print("=" * 60)
    
    try:
        # 读取SSO服务代码
        with open("services/sso/main.py", "r") as f:
            sso_code = f.read()
        
        # 检查关键功能
        checks = [
            ("create_id_token导入", "create_id_token" in sso_code),
            ("ID Token生成", "create_id_token(id_token_data, request.client_id)" in sso_code),
            ("UserInfo端点", "@app.get(\"/api/v1/sso/userinfo\")" in sso_code),
            ("从数据库获取用户", "db.query(User).filter(User.id == user_id).first()" in sso_code),
            ("返回OpenID Connect用户信息", "\"preferred_username\"" in sso_code),
            ("Authorization header处理", "authorization: str = Header(None)" in sso_code),
            ("用户ID存储在授权码中", "f\"{client_id}:{redirect_uri}:{user_id}\"" in sso_code),
        ]
        
        all_passed = True
        for check_name, result in checks:
            if result:
                print(f"✓ {check_name}")
            else:
                print(f"✗ {check_name}")
                all_passed = False
        
        if all_passed:
            print("\n" + "=" * 60)
            print("✓ SSO服务代码结构验证通过")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("✗ SSO服务代码结构验证失败")
            print("=" * 60)
        
        return all_passed
        
    except Exception as e:
        print(f"✗ 验证失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("OpenID Connect实现验证")
    print("=" * 60 + "\n")
    
    results = []
    
    # 验证ID Token函数
    results.append(("ID Token生成函数", verify_id_token_function()))
    
    # 验证SSO服务代码
    results.append(("SSO服务代码结构", verify_sso_service_code()))
    
    # 总结
    print("\n" + "=" * 60)
    print("验证总结")
    print("=" * 60)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(result for _, result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ 所有验证通过！OpenID Connect实现正确。")
    else:
        print("✗ 部分验证失败，请检查实现。")
    print("=" * 60 + "\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
