"""
云服务配置接口测试

测试任务 14.1：实现云服务配置接口
- 实现配置列表查询（GET /api/v1/admin/cloud-services）
- 实现配置创建（POST /api/v1/admin/cloud-services）
- 实现配置更新（PUT /api/v1/admin/cloud-services/{config_id}）
- 实现配置加密存储
- 验证需求：8.1, 8.2

测试任务 14.2：实现配置验证功能
- 配置创建和更新时会自动验证配置有效性
- 验证需求：8.5
"""
import pytest
import sys
import os
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid
from unittest.mock import patch, MagicMock

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database import Base
from shared.models.user import User
from shared.models.permission import Role, UserRole
from shared.models.system import CloudServiceConfig
from shared.utils.crypto import hash_password, encrypt_config, decrypt_config
from services.admin.main import app
from fastapi.testclient import TestClient


# 测试数据库设置
TEST_DATABASE_URL = "sqlite:///./test_cloud_service_config.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """创建测试数据库会话"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def super_admin_user(db):
    """创建超级管理员用户"""
    # 创建超级管理员角色
    super_admin_role = Role(
        name="super_admin",
        description="超级管理员",
        is_system_role=True
    )
    db.add(super_admin_role)
    db.flush()
    
    # 创建超级管理员用户
    admin_user = User(
        username="admin",
        email="admin@example.com",
        password_hash=hash_password("123456"),
        status="active"
    )
    db.add(admin_user)
    db.flush()
    
    # 分配超级管理员角色
    user_role = UserRole(
        user_id=admin_user.id,
        role_id=super_admin_role.id
    )
    db.add(user_role)
    db.commit()
    db.refresh(admin_user)
    
    return admin_user


@pytest.fixture
def regular_user(db):
    """创建普通用户"""
    user = User(
        username="regular_user",
        email="user@example.com",
        password_hash=hash_password("password123"),
        status="active"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def override_get_db():
    """覆盖数据库依赖"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# 覆盖依赖
from shared.database import get_db
app.dependency_overrides[get_db] = override_get_db


class TestCloudServiceConfigList:
    """测试云服务配置列表查询"""
    
    def test_list_configs_as_super_admin(self, client, super_admin_user, db):
        """测试超级管理员可以查询配置列表"""
        # 创建测试配置
        config1 = CloudServiceConfig(
            service_type="email",
            provider="aliyun",
            config=encrypt_config({
                "smtp_host": "smtp.aliyun.com",
                "smtp_port": 465,
                "username": "test@example.com",
                "password": "test_password"
            }),
            is_active=True
        )
        config2 = CloudServiceConfig(
            service_type="sms",
            provider="tencent",
            config=encrypt_config({
                "api_key": "test_api_key",
                "api_secret": "test_api_secret"
            }),
            is_active=True
        )
        db.add_all([config1, config2])
        db.commit()
        
        # 查询配置列表
        response = client.get(
            "/api/v1/admin/cloud-services",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["configs"]) == 2
        
        # 验证配置已解密
        email_config = next(c for c in data["configs"] if c["service_type"] == "email")
        assert email_config["provider"] == "aliyun"
        assert "smtp_host" in email_config["config"]
        assert email_config["config"]["smtp_host"] == "smtp.aliyun.com"
    
    def test_list_configs_with_filter(self, client, super_admin_user, db):
        """测试带过滤条件的配置列表查询"""
        # 创建测试配置
        config1 = CloudServiceConfig(
            service_type="email",
            provider="aliyun",
            config=encrypt_config({"test": "data1"}),
            is_active=True
        )
        config2 = CloudServiceConfig(
            service_type="sms",
            provider="tencent",
            config=encrypt_config({"test": "data2"}),
            is_active=True
        )
        db.add_all([config1, config2])
        db.commit()
        
        # 按服务类型过滤
        response = client.get(
            "/api/v1/admin/cloud-services",
            params={
                "user_id": str(super_admin_user.id),
                "service_type": "email"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["configs"][0]["service_type"] == "email"
    
    def test_list_configs_as_regular_user_forbidden(self, client, regular_user):
        """测试普通用户无法查询配置列表"""
        response = client.get(
            "/api/v1/admin/cloud-services",
            params={"user_id": str(regular_user.id)}
        )
        
        assert response.status_code == 403
        assert "只有超级管理员" in response.json()["detail"]


class TestCloudServiceConfigCreate:
    """测试云服务配置创建"""
    
    @patch('services.admin.main.validate_cloud_service_config')
    def test_create_email_config(self, mock_validate, client, super_admin_user, db):
        """测试创建邮件服务配置"""
        # Mock配置验证成功
        mock_validate.return_value = (True, "配置验证成功")
        
        config_data = {
            "service_type": "email",
            "provider": "aliyun",
            "config": {
                "smtp_host": "smtp.aliyun.com",
                "smtp_port": 465,
                "username": "noreply@example.com",
                "password": "secure_password",
                "use_ssl": True
            },
            "is_active": True
        }
        
        response = client.post(
            "/api/v1/admin/cloud-services",
            json=config_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["service_type"] == "email"
        assert data["provider"] == "aliyun"
        assert data["config"]["smtp_host"] == "smtp.aliyun.com"
        assert data["is_active"] is True
        assert "id" in data
        
        # 验证数据库中的配置已加密
        config_id = uuid.UUID(data["id"])
        db_config = db.query(CloudServiceConfig).filter(CloudServiceConfig.id == config_id).first()
        assert db_config is not None
        
        # 配置应该是加密的字符串
        assert isinstance(db_config.config, str)
        
        # 解密后应该能得到原始配置
        decrypted = decrypt_config(db_config.config)
        assert decrypted["smtp_host"] == "smtp.aliyun.com"
        assert decrypted["password"] == "secure_password"
    
    @patch('services.admin.main.validate_cloud_service_config')
    def test_create_sms_config(self, mock_validate, client, super_admin_user, db):
        """测试创建短信服务配置"""
        # Mock配置验证成功
        mock_validate.return_value = (True, "配置验证成功")
        
        config_data = {
            "service_type": "sms",
            "provider": "tencent",
            "config": {
                "api_key": "test_api_key",
                "api_secret": "test_api_secret",
                "sign_name": "测试签名"
            },
            "is_active": True
        }
        
        response = client.post(
            "/api/v1/admin/cloud-services",
            json=config_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["service_type"] == "sms"
        assert data["provider"] == "tencent"
        assert data["config"]["api_key"] == "test_api_key"
    
    def test_create_config_duplicate_fails(self, client, super_admin_user, db):
        """测试创建重复配置失败"""
        # 先创建一个配置
        config = CloudServiceConfig(
            service_type="email",
            provider="aliyun",
            config=encrypt_config({"test": "data"}),
            is_active=True
        )
        db.add(config)
        db.commit()
        
        # 尝试创建相同的配置
        config_data = {
            "service_type": "email",
            "provider": "aliyun",
            "config": {"test": "new_data"},
            "is_active": True
        }
        
        response = client.post(
            "/api/v1/admin/cloud-services",
            json=config_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 409
        assert "已存在" in response.json()["detail"]
    
    def test_create_config_invalid_service_type(self, client, super_admin_user):
        """测试创建无效服务类型的配置失败"""
        config_data = {
            "service_type": "invalid_type",
            "provider": "aliyun",
            "config": {"test": "data"},
            "is_active": True
        }
        
        response = client.post(
            "/api/v1/admin/cloud-services",
            json=config_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 400
        assert "无效的服务类型" in response.json()["detail"]
    
    @patch('services.admin.main.validate_cloud_service_config')
    def test_create_config_as_regular_user_forbidden(self, mock_validate, client, regular_user):
        """测试普通用户无法创建配置"""
        # Mock配置验证成功（虽然不会被调用，因为权限检查会先失败）
        mock_validate.return_value = (True, "配置验证成功")
        
        config_data = {
            "service_type": "email",
            "provider": "aliyun",
            "config": {"test": "data"},
            "is_active": True
        }
        
        response = client.post(
            "/api/v1/admin/cloud-services",
            json=config_data,
            params={"user_id": str(regular_user.id)}
        )
        
        assert response.status_code == 403
    
    def test_create_config_validation_failure(self, client, super_admin_user):
        """测试配置验证失败"""
        config_data = {
            "service_type": "email",
            "provider": "aliyun",
            "config": {
                "smtp_host": "smtp.example.com",
                "smtp_port": 465,
                # 缺少username和password
            },
            "is_active": True
        }
        
        response = client.post(
            "/api/v1/admin/cloud-services",
            json=config_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 422
        assert "配置验证失败" in response.json()["detail"]


class TestCloudServiceConfigUpdate:
    """测试云服务配置更新"""
    
    @patch('services.admin.main.validate_cloud_service_config')
    def test_update_config(self, mock_validate, client, super_admin_user, db):
        """测试更新配置"""
        # Mock配置验证成功
        mock_validate.return_value = (True, "配置验证成功")
        
        # 创建初始配置
        config = CloudServiceConfig(
            service_type="email",
            provider="aliyun",
            config=encrypt_config({
                "smtp_host": "smtp.aliyun.com",
                "smtp_port": 465
            }),
            is_active=True
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        
        # 更新配置
        update_data = {
            "config": {
                "smtp_host": "smtp.aliyun.com",
                "smtp_port": 587,
                "username": "new_user@example.com"
            },
            "is_active": False
        }
        
        response = client.put(
            f"/api/v1/admin/cloud-services/{config.id}",
            json=update_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["config"]["smtp_port"] == 587
        assert data["config"]["username"] == "new_user@example.com"
        assert data["is_active"] is False
        
        # 验证数据库中的配置已更新并加密
        db.refresh(config)
        decrypted = decrypt_config(config.config)
        assert decrypted["smtp_port"] == 587
        assert decrypted["username"] == "new_user@example.com"
    
    def test_update_config_partial(self, client, super_admin_user, db):
        """测试部分更新配置"""
        # 创建初始配置
        config = CloudServiceConfig(
            service_type="email",
            provider="aliyun",
            config=encrypt_config({"smtp_host": "smtp.aliyun.com"}),
            is_active=True
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        
        # 只更新is_active
        update_data = {
            "is_active": False
        }
        
        response = client.put(
            f"/api/v1/admin/cloud-services/{config.id}",
            json=update_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False
        # 配置内容应该保持不变
        assert data["config"]["smtp_host"] == "smtp.aliyun.com"
    
    def test_update_nonexistent_config(self, client, super_admin_user):
        """测试更新不存在的配置"""
        fake_id = str(uuid.uuid4())
        update_data = {
            "is_active": False
        }
        
        response = client.put(
            f"/api/v1/admin/cloud-services/{fake_id}",
            json=update_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 404
        assert "不存在" in response.json()["detail"]
    
    def test_update_config_as_regular_user_forbidden(self, client, regular_user, db):
        """测试普通用户无法更新配置"""
        # 创建配置
        config = CloudServiceConfig(
            service_type="email",
            provider="aliyun",
            config=encrypt_config({"test": "data"}),
            is_active=True
        )
        db.add(config)
        db.commit()
        
        update_data = {
            "is_active": False
        }
        
        response = client.put(
            f"/api/v1/admin/cloud-services/{config.id}",
            json=update_data,
            params={"user_id": str(regular_user.id)}
        )
        
        assert response.status_code == 403


class TestCloudServiceConfigDelete:
    """测试云服务配置删除"""
    
    def test_delete_config(self, client, super_admin_user, db):
        """测试删除配置"""
        # 创建配置
        config = CloudServiceConfig(
            service_type="email",
            provider="aliyun",
            config=encrypt_config({"test": "data"}),
            is_active=True
        )
        db.add(config)
        db.commit()
        config_id = config.id
        
        # 删除配置
        response = client.delete(
            f"/api/v1/admin/cloud-services/{config_id}",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        assert response.json()["success"] is True
        
        # 验证配置已从数据库删除
        deleted_config = db.query(CloudServiceConfig).filter(CloudServiceConfig.id == config_id).first()
        assert deleted_config is None
    
    def test_delete_nonexistent_config(self, client, super_admin_user):
        """测试删除不存在的配置"""
        fake_id = str(uuid.uuid4())
        
        response = client.delete(
            f"/api/v1/admin/cloud-services/{fake_id}",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 404


class TestConfigEncryption:
    """测试配置加密功能"""
    
    def test_config_encryption_decryption(self):
        """测试配置加密和解密"""
        original_config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "username": "test@example.com",
            "password": "super_secret_password",
            "use_ssl": True
        }
        
        # 加密
        encrypted = encrypt_config(original_config)
        assert isinstance(encrypted, str)
        assert encrypted != str(original_config)
        
        # 解密
        decrypted = decrypt_config(encrypted)
        assert decrypted == original_config
        assert decrypted["password"] == "super_secret_password"
    
    def test_config_encryption_with_special_characters(self):
        """测试包含特殊字符的配置加密"""
        original_config = {
            "api_key": "test!@#$%^&*()_+-=[]{}|;:',.<>?/",
            "api_secret": "中文密钥测试",
            "nested": {
                "key1": "value1",
                "key2": 123
            }
        }
        
        encrypted = encrypt_config(original_config)
        decrypted = decrypt_config(encrypted)
        
        assert decrypted == original_config
        assert decrypted["api_key"] == "test!@#$%^&*()_+-=[]{}|;:',.<>?/"
        assert decrypted["api_secret"] == "中文密钥测试"
        assert decrypted["nested"]["key2"] == 123


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
