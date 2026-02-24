"""
单元测试：首次登录密码修改

测试首次登录检测和强制密码修改流程

验证需求：6.6
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from shared.database import SessionLocal, engine, Base
from shared.models.user import User, RefreshToken
from shared.utils.crypto import hash_password
from services.auth.main import app

# 创建测试客户端
client = TestClient(app)


@pytest.fixture(scope="function")
def db_session():
    """创建测试数据库会话"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def user_with_unchanged_password(db_session):
    """创建一个未修改初始密码的用户"""
    user = User(
        username="newuser",
        email="newuser@test.com",
        password_hash=hash_password("InitialPass123!"),
        status="active",
        password_changed=False,  # 未修改初始密码
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def user_with_changed_password(db_session):
    """创建一个已修改密码的用户"""
    user = User(
        username="existinguser",
        email="existing@test.com",
        password_hash=hash_password("CurrentPass123!"),
        status="active",
        password_changed=True,  # 已修改密码
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestFirstLoginPasswordChange:
    """测试首次登录密码修改功能"""
    
    def test_check_first_login_requires_password_change(
        self,
        user_with_unchanged_password,
        db_session
    ):
        """
        测试：检查首次登录用户需要修改密码
        
        验证需求：6.6 - 首次登录检测
        """
        user_id = str(user_with_unchanged_password.id)
        
        response = client.get(f"/api/v1/auth/check-first-login/{user_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["requires_password_change"] is True
        assert "需要修改密码" in data["message"]
    
    def test_check_first_login_password_already_changed(
        self,
        user_with_changed_password,
        db_session
    ):
        """
        测试：检查已修改密码的用户不需要再次修改
        
        验证需求：6.6 - 首次登录检测
        """
        user_id = str(user_with_changed_password.id)
        
        response = client.get(f"/api/v1/auth/check-first-login/{user_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["requires_password_change"] is False
        assert "密码已修改" in data["message"]
    
    def test_check_first_login_invalid_user_id(self, db_session):
        """
        测试：检查首次登录时使用无效的用户ID
        """
        response = client.get("/api/v1/auth/check-first-login/invalid-uuid")
        
        assert response.status_code == 422
        assert "无效的用户ID格式" in response.json()["detail"]
    
    def test_check_first_login_nonexistent_user(self, db_session):
        """
        测试：检查首次登录时用户不存在
        """
        fake_user_id = str(uuid.uuid4())
        
        response = client.get(f"/api/v1/auth/check-first-login/{fake_user_id}")
        
        assert response.status_code == 404
        assert "用户不存在" in response.json()["detail"]
    
    def test_change_password_success(
        self,
        user_with_unchanged_password,
        db_session
    ):
        """
        测试：成功修改密码
        
        验证需求：6.6 - 强制密码修改流程
        """
        user_id = str(user_with_unchanged_password.id)
        
        response = client.post(
            "/api/v1/auth/change-password",
            params={"user_id": user_id},
            json={
                "old_password": "InitialPass123!",
                "new_password": "NewSecurePass456!"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "密码修改成功" in data["message"]
        
        # 验证数据库中的password_changed字段已更新
        db_session.refresh(user_with_unchanged_password)
        assert user_with_unchanged_password.password_changed is True
        
        # 验证新密码可以使用
        from shared.utils.crypto import verify_password
        assert verify_password(
            "NewSecurePass456!",
            user_with_unchanged_password.password_hash
        )
    
    def test_change_password_wrong_old_password(
        self,
        user_with_unchanged_password,
        db_session
    ):
        """
        测试：修改密码时旧密码错误
        """
        user_id = str(user_with_unchanged_password.id)
        
        response = client.post(
            "/api/v1/auth/change-password",
            params={"user_id": user_id},
            json={
                "old_password": "WrongPassword123!",
                "new_password": "NewSecurePass456!"
            }
        )
        
        assert response.status_code == 401
        assert "旧密码不正确" in response.json()["detail"]
        
        # 验证password_changed字段未更新
        db_session.refresh(user_with_unchanged_password)
        assert user_with_unchanged_password.password_changed is False
    
    def test_change_password_weak_new_password(
        self,
        user_with_unchanged_password,
        db_session
    ):
        """
        测试：修改密码时新密码强度不足
        """
        user_id = str(user_with_unchanged_password.id)
        
        # 测试太短的密码
        response = client.post(
            "/api/v1/auth/change-password",
            params={"user_id": user_id},
            json={
                "old_password": "InitialPass123!",
                "new_password": "weak"
            }
        )
        
        assert response.status_code == 400
        assert "密码" in response.json()["detail"]
    
    def test_change_password_same_as_old(
        self,
        user_with_unchanged_password,
        db_session
    ):
        """
        测试：修改密码时新密码与旧密码相同
        """
        user_id = str(user_with_unchanged_password.id)
        
        response = client.post(
            "/api/v1/auth/change-password",
            params={"user_id": user_id},
            json={
                "old_password": "InitialPass123!",
                "new_password": "InitialPass123!"
            }
        )
        
        assert response.status_code == 400
        assert "新密码不能与旧密码相同" in response.json()["detail"]
    
    def test_change_password_revokes_refresh_tokens(
        self,
        user_with_unchanged_password,
        db_session
    ):
        """
        测试：修改密码后撤销所有Refresh Token
        
        验证需求：6.6 - 强制重新登录
        """
        user_id = str(user_with_unchanged_password.id)
        
        # 创建一些Refresh Token
        token1 = RefreshToken(
            user_id=user_with_unchanged_password.id,
            token_hash="hash1",
            expires_at=datetime.utcnow(),
            revoked=False,
            created_at=datetime.utcnow()
        )
        token2 = RefreshToken(
            user_id=user_with_unchanged_password.id,
            token_hash="hash2",
            expires_at=datetime.utcnow(),
            revoked=False,
            created_at=datetime.utcnow()
        )
        db_session.add(token1)
        db_session.add(token2)
        db_session.commit()
        
        # 修改密码
        response = client.post(
            "/api/v1/auth/change-password",
            params={"user_id": user_id},
            json={
                "old_password": "InitialPass123!",
                "new_password": "NewSecurePass456!"
            }
        )
        
        assert response.status_code == 200
        
        # 验证所有Refresh Token都被撤销
        tokens = db_session.query(RefreshToken).filter(
            RefreshToken.user_id == user_with_unchanged_password.id
        ).all()
        
        for token in tokens:
            assert token.revoked is True, "所有Refresh Token应该被撤销"
            assert token.revoked_at is not None
    
    def test_change_password_invalid_user_id(self, db_session):
        """
        测试：修改密码时使用无效的用户ID
        """
        response = client.post(
            "/api/v1/auth/change-password",
            params={"user_id": "invalid-uuid"},
            json={
                "old_password": "OldPass123!",
                "new_password": "NewPass456!"
            }
        )
        
        assert response.status_code == 422
        assert "无效的用户ID格式" in response.json()["detail"]
    
    def test_change_password_nonexistent_user(self, db_session):
        """
        测试：修改密码时用户不存在
        """
        fake_user_id = str(uuid.uuid4())
        
        response = client.post(
            "/api/v1/auth/change-password",
            params={"user_id": fake_user_id},
            json={
                "old_password": "OldPass123!",
                "new_password": "NewPass456!"
            }
        )
        
        assert response.status_code == 404
        assert "用户不存在" in response.json()["detail"]
    
    def test_login_response_includes_password_change_flag(
        self,
        user_with_unchanged_password,
        db_session
    ):
        """
        测试：登录响应包含密码修改标记
        
        验证需求：6.6 - 首次登录检测
        """
        # 登录
        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": "newuser@test.com",
                "password": "InitialPass123!"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 验证响应包含requires_password_change标记
        assert "user" in data
        assert "requires_password_change" in data["user"]
        assert data["user"]["requires_password_change"] is True
    
    def test_super_admin_initial_password_unchanged(self, db_session):
        """
        测试：超级管理员初始密码未修改
        
        验证需求：6.1, 6.6 - 系统初始化时创建的超级管理员需要修改密码
        """
        # 创建超级管理员（模拟系统初始化）
        admin = User(
            username="admin",
            email="admin@unified-auth.local",
            password_hash=hash_password("123456"),
            status="active",
            password_changed=False,  # 初始密码未修改
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(admin)
        db_session.commit()
        
        # 检查首次登录状态
        response = client.get(f"/api/v1/auth/check-first-login/{str(admin.id)}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["requires_password_change"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
