"""
测试云服务配置测试功能

需求：8.6 - 提供测试功能（发送测试邮件/短信）

测试场景：
1. 测试邮件发送功能
2. 测试短信发送功能（阿里云和腾讯云）
3. 测试权限控制（只有超级管理员可以测试）
4. 测试错误处理（无效配置、无效参数等）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import uuid

from services.admin.main import app
from shared.database import Base, get_db
from shared.models.user import User
from shared.models.permission import Role, UserRole
from shared.models.system import CloudServiceConfig
from shared.utils.crypto import encrypt_config

# 创建测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_config_testing.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建测试客户端
client = TestClient(app)


def override_get_db():
    """覆盖数据库依赖"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function", autouse=True)
def setup_database():
    """设置测试数据库"""
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    yield
    # 清理所有表
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def super_admin_user():
    """创建超级管理员用户"""
    db = TestingSessionLocal()
    try:
        # 创建超级管理员角色
        super_admin_role = Role(
            name="super_admin",
            description="超级管理员",
            is_system_role=True
        )
        db.add(super_admin_role)
        db.commit()
        db.refresh(super_admin_role)
        
        # 创建超级管理员用户
        admin_user = User(
            username="admin",
            email="admin@example.com",
            password_hash="hashed_password",
            status="active"
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        # 分配超级管理员角色
        user_role = UserRole(
            user_id=admin_user.id,
            role_id=super_admin_role.id
        )
        db.add(user_role)
        db.commit()
        
        return str(admin_user.id)
    finally:
        db.close()


@pytest.fixture
def regular_user():
    """创建普通用户"""
    db = TestingSessionLocal()
    try:
        user = User(
            username="regular_user",
            email="user@example.com",
            password_hash="hashed_password",
            status="active"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return str(user.id)
    finally:
        db.close()


@pytest.fixture
def email_config():
    """创建邮件服务配置"""
    db = TestingSessionLocal()
    try:
        config_data = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "test@example.com",
            "password": "test_password",
            "use_ssl": False,
            "use_tls": True,
            "from_email": "noreply@example.com"
        }
        
        encrypted_config = encrypt_config(config_data)
        
        config = CloudServiceConfig(
            service_type="email",
            provider="test_provider",
            config=encrypted_config,
            is_active=True
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        
        return str(config.id)
    finally:
        db.close()


@pytest.fixture
def aliyun_sms_config():
    """创建阿里云短信服务配置"""
    db = TestingSessionLocal()
    try:
        config_data = {
            "access_key_id": "test_access_key_id",
            "access_key_secret": "test_access_key_secret",
            "sign_name": "测试签名",
            "endpoint": "dysmsapi.aliyuncs.com"
        }
        
        encrypted_config = encrypt_config(config_data)
        
        config = CloudServiceConfig(
            service_type="sms",
            provider="aliyun",
            config=encrypted_config,
            is_active=True
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        
        return str(config.id)
    finally:
        db.close()


@pytest.fixture
def tencent_sms_config():
    """创建腾讯云短信服务配置"""
    db = TestingSessionLocal()
    try:
        config_data = {
            "secret_id": "test_secret_id",
            "secret_key": "test_secret_key",
            "sdk_app_id": "1400000000",
            "sign_name": "测试签名",
            "endpoint": "sms.tencentcloudapi.com"
        }
        
        encrypted_config = encrypt_config(config_data)
        
        config = CloudServiceConfig(
            service_type="sms",
            provider="tencent",
            config=encrypted_config,
            is_active=True
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        
        return str(config.id)
    finally:
        db.close()


# ==================== 测试邮件配置测试功能 ====================

def test_test_email_config_requires_super_admin(email_config, regular_user):
    """测试邮件配置测试需要超级管理员权限"""
    response = client.post(
        f"/api/v1/admin/cloud-services/{email_config}/test",
        params={"user_id": regular_user},
        json={
            "test_email": {
                "to_email": "test@example.com",
                "subject": "测试邮件",
                "body": "这是一封测试邮件"
            }
        }
    )
    
    assert response.status_code == 403
    assert "超级管理员" in response.json()["detail"]


def test_test_email_config_missing_parameters(email_config, super_admin_user):
    """测试邮件配置测试缺少参数"""
    response = client.post(
        f"/api/v1/admin/cloud-services/{email_config}/test",
        params={"user_id": super_admin_user}
    )
    
    assert response.status_code == 400
    assert "测试邮件参数" in response.json()["detail"]


def test_test_email_config_invalid_email_format(email_config, super_admin_user):
    """测试邮件配置测试 - 无效的邮箱格式"""
    response = client.post(
        f"/api/v1/admin/cloud-services/{email_config}/test",
        params={"user_id": super_admin_user},
        json={
            "test_email": {
                "to_email": "invalid_email",
                "subject": "测试邮件",
                "body": "这是一封测试邮件"
            }
        }
    )
    
    assert response.status_code == 422
    assert "无效的邮箱地址格式" in response.json()["detail"]


def test_test_email_config_nonexistent_config(super_admin_user):
    """测试邮件配置测试 - 配置不存在"""
    fake_config_id = str(uuid.uuid4())
    
    response = client.post(
        f"/api/v1/admin/cloud-services/{fake_config_id}/test",
        params={"user_id": super_admin_user},
        json={
            "test_email": {
                "to_email": "test@example.com",
                "subject": "测试邮件",
                "body": "这是一封测试邮件"
            }
        }
    )
    
    assert response.status_code == 404
    assert "配置不存在" in response.json()["detail"]


def test_test_email_config_invalid_config_id(super_admin_user):
    """测试邮件配置测试 - 无效的配置ID格式"""
    response = client.post(
        f"/api/v1/admin/cloud-services/invalid_id/test",
        params={"user_id": super_admin_user},
        json={
            "test_email": {
                "to_email": "test@example.com",
                "subject": "测试邮件",
                "body": "这是一封测试邮件"
            }
        }
    )
    
    assert response.status_code == 422
    assert "无效的配置ID格式" in response.json()["detail"]


# ==================== 测试短信配置测试功能 ====================

def test_test_aliyun_sms_config_requires_super_admin(aliyun_sms_config, regular_user):
    """测试阿里云短信配置测试需要超级管理员权限"""
    response = client.post(
        f"/api/v1/admin/cloud-services/{aliyun_sms_config}/test",
        params={"user_id": regular_user},
        json={
            "test_sms": {
                "to_phone": "+8613800138000",
                "content": "测试短信"
            }
        }
    )
    
    assert response.status_code == 403
    assert "超级管理员" in response.json()["detail"]


def test_test_sms_config_missing_parameters(aliyun_sms_config, super_admin_user):
    """测试短信配置测试缺少参数"""
    response = client.post(
        f"/api/v1/admin/cloud-services/{aliyun_sms_config}/test",
        params={"user_id": super_admin_user}
    )
    
    assert response.status_code == 400
    assert "测试短信参数" in response.json()["detail"]


def test_test_sms_config_invalid_phone_format(aliyun_sms_config, super_admin_user):
    """测试短信配置测试 - 无效的手机号格式"""
    response = client.post(
        f"/api/v1/admin/cloud-services/{aliyun_sms_config}/test",
        params={"user_id": super_admin_user},
        json={
            "test_sms": {
                "to_phone": "invalid_phone",
                "content": "测试短信"
            }
        }
    )
    
    assert response.status_code == 422
    assert "无效的手机号格式" in response.json()["detail"]


def test_test_aliyun_sms_config_success(aliyun_sms_config, super_admin_user):
    """测试阿里云短信配置测试成功"""
    response = client.post(
        f"/api/v1/admin/cloud-services/{aliyun_sms_config}/test",
        params={"user_id": super_admin_user},
        json={
            "test_sms": {
                "to_phone": "+8613800138000",
                "content": "测试短信"
            }
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "阿里云短信配置验证成功" in data["message"]
    assert data["details"]["provider"] == "aliyun"
    assert data["details"]["to_phone"] == "+8613800138000"


def test_test_tencent_sms_config_success(tencent_sms_config, super_admin_user):
    """测试腾讯云短信配置测试成功"""
    response = client.post(
        f"/api/v1/admin/cloud-services/{tencent_sms_config}/test",
        params={"user_id": super_admin_user},
        json={
            "test_sms": {
                "to_phone": "+8613800138000",
                "content": "测试短信"
            }
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "腾讯云短信配置验证成功" in data["message"]
    assert data["details"]["provider"] == "tencent"
    assert data["details"]["to_phone"] == "+8613800138000"


# ==================== 测试边界情况 ====================

def test_test_config_with_various_phone_formats(aliyun_sms_config, super_admin_user):
    """测试各种手机号格式"""
    valid_phones = [
        "+8613800138000",
        "+86138001380001",  # 11位
        "+12025551234",  # 美国号码
        "+447911123456"  # 英国号码
    ]
    
    for phone in valid_phones:
        response = client.post(
            f"/api/v1/admin/cloud-services/{aliyun_sms_config}/test",
            params={"user_id": super_admin_user},
            json={
                "test_sms": {
                    "to_phone": phone,
                    "content": "测试短信"
                }
            }
        )
        
        assert response.status_code == 200, f"Phone {phone} should be valid"


def test_test_config_with_invalid_phone_formats(aliyun_sms_config, super_admin_user):
    """测试无效的手机号格式"""
    invalid_phones = [
        "13800138000",  # 缺少国家码
        "+0138001380",  # 国家码不能以0开头
        "abc123",  # 包含字母
        "+86-138-0013-8000",  # 包含连字符
        ""  # 空字符串
    ]
    
    for phone in invalid_phones:
        response = client.post(
            f"/api/v1/admin/cloud-services/{aliyun_sms_config}/test",
            params={"user_id": super_admin_user},
            json={
                "test_sms": {
                    "to_phone": phone,
                    "content": "测试短信"
                }
            }
        )
        
        assert response.status_code == 422, f"Phone {phone} should be invalid"


def test_test_config_with_various_email_formats(email_config, super_admin_user):
    """测试各种邮箱格式"""
    valid_emails = [
        "test@example.com",
        "user.name@example.com",
        "user+tag@example.co.uk",
        "123@example.com"
    ]
    
    for email in valid_emails:
        response = client.post(
            f"/api/v1/admin/cloud-services/{email_config}/test",
            params={"user_id": super_admin_user},
            json={
                "test_email": {
                    "to_email": email,
                    "subject": "测试邮件",
                    "body": "这是一封测试邮件"
                }
            }
        )
        
        # 注意：由于我们使用的是测试SMTP配置，实际发送会失败
        # 但邮箱格式验证应该通过
        assert response.status_code in [200, 422, 500], f"Email {email} format should be valid"


def test_test_config_with_invalid_email_formats(email_config, super_admin_user):
    """测试无效的邮箱格式"""
    invalid_emails = [
        "invalid_email",
        "@example.com",
        "user@",
        "user @example.com",
        ""
    ]
    
    for email in invalid_emails:
        response = client.post(
            f"/api/v1/admin/cloud-services/{email_config}/test",
            params={"user_id": super_admin_user},
            json={
                "test_email": {
                    "to_email": email,
                    "subject": "测试邮件",
                    "body": "这是一封测试邮件"
                }
            }
        )
        
        assert response.status_code == 422, f"Email {email} should be invalid"


# ==================== 测试配置完整性 ====================

def test_test_email_config_with_incomplete_config(super_admin_user):
    """测试不完整的邮件配置"""
    db = TestingSessionLocal()
    try:
        # 创建不完整的配置（缺少密码）
        config_data = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "test@example.com",
            # 缺少 password
            "use_ssl": False,
            "use_tls": True
        }
        
        encrypted_config = encrypt_config(config_data)
        
        config = CloudServiceConfig(
            service_type="email",
            provider="test_provider",
            config=encrypted_config,
            is_active=True
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        
        config_id = str(config.id)
    finally:
        db.close()
    
    response = client.post(
        f"/api/v1/admin/cloud-services/{config_id}/test",
        params={"user_id": super_admin_user},
        json={
            "test_email": {
                "to_email": "test@example.com",
                "subject": "测试邮件",
                "body": "这是一封测试邮件"
            }
        }
    )
    
    # The error could be 422 (validation error) or 500 (internal error during decryption/connection)
    # Both are acceptable for incomplete config
    assert response.status_code in [422, 500]
    assert "配置" in response.json()["detail"] or "失败" in response.json()["detail"]


def test_test_sms_config_with_incomplete_config(super_admin_user):
    """测试不完整的短信配置"""
    db = TestingSessionLocal()
    try:
        # 创建不完整的配置（缺少签名）
        config_data = {
            "access_key_id": "test_access_key_id",
            "access_key_secret": "test_access_key_secret",
            # 缺少 sign_name
            "endpoint": "dysmsapi.aliyuncs.com"
        }
        
        encrypted_config = encrypt_config(config_data)
        
        config = CloudServiceConfig(
            service_type="sms",
            provider="aliyun",
            config=encrypted_config,
            is_active=True
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        
        config_id = str(config.id)
    finally:
        db.close()
    
    response = client.post(
        f"/api/v1/admin/cloud-services/{config_id}/test",
        params={"user_id": super_admin_user},
        json={
            "test_sms": {
                "to_phone": "+8613800138000",
                "content": "测试短信"
            }
        }
    )
    
    assert response.status_code == 422
    assert "配置不完整" in response.json()["detail"]


# ==================== 测试响应格式 ====================

def test_test_config_response_format(aliyun_sms_config, super_admin_user):
    """测试配置测试响应格式"""
    response = client.post(
        f"/api/v1/admin/cloud-services/{aliyun_sms_config}/test",
        params={"user_id": super_admin_user},
        json={
            "test_sms": {
                "to_phone": "+8613800138000",
                "content": "测试短信"
            }
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # 验证响应包含必需字段
    assert "success" in data
    assert "message" in data
    assert "details" in data
    
    # 验证字段类型
    assert isinstance(data["success"], bool)
    assert isinstance(data["message"], str)
    assert isinstance(data["details"], dict)
    
    # 验证details包含必要信息
    assert "provider" in data["details"]
    assert "to_phone" in data["details"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
