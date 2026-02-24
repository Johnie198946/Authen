"""
API测试脚本
"""
import requests
import json

BASE_URL = "http://localhost:8001"

def test_email_registration():
    """测试邮箱注册"""
    print("\n=== 测试邮箱注册 ===")
    
    data = {
        "email": "test@example.com",
        "password": "TestPass123!",
        "username": "testuser"
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/auth/register/email", json=data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    return response.json()


def test_phone_registration():
    """测试手机注册"""
    print("\n=== 测试手机注册 ===")
    
    # 1. 发送验证码
    print("\n1. 发送短信验证码")
    phone_data = {"phone": "+8613800138000"}
    response = requests.post(f"{BASE_URL}/api/v1/auth/send-sms", json=phone_data)
    print(f"状态码: {response.status_code}")
    result = response.json()
    print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    if response.status_code == 200 and result.get("code"):
        # 2. 使用验证码注册
        print("\n2. 使用验证码注册")
        register_data = {
            "phone": "+8613800138000",
            "password": "TestPass123!",
            "username": "phoneuser",
            "verification_code": result["code"]
        }
        
        response = requests.post(f"{BASE_URL}/api/v1/auth/register/phone", json=register_data)
        print(f"状态码: {response.status_code}")
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        return response.json()


def test_login():
    """测试登录"""
    print("\n=== 测试登录 ===")
    
    data = {
        "identifier": "+8613800138000",
        "password": "TestPass123!"
    }
    
    response = requests.post(f"{BASE_URL}/api/v1/auth/login", json=data)
    print(f"状态码: {response.status_code}")
    result = response.json()
    print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    return result


def test_token_refresh(refresh_token):
    """测试Token刷新"""
    print("\n=== 测试Token刷新 ===")
    
    data = {"refresh_token": refresh_token}
    
    response = requests.post(f"{BASE_URL}/api/v1/auth/refresh", json=data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")


def main():
    """主测试流程"""
    print("🚀 开始测试认证服务API")
    print(f"服务地址: {BASE_URL}")
    
    try:
        # 测试邮箱注册
        # test_email_registration()
        
        # 测试手机注册
        test_phone_registration()
        
        # 测试登录
        login_result = test_login()
        
        # 测试Token刷新
        if "refresh_token" in login_result:
            test_token_refresh(login_result["refresh_token"])
        
        print("\n✅ 所有测试完成！")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ 错误：无法连接到服务器")
        print("请确保认证服务正在运行：python3 services/auth/main.py")
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")


if __name__ == "__main__":
    main()
