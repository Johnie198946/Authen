"""
OAuth认证功能测试

需求：1.3 - 通过OAuth协议完成认证并创建或关联账号
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta

from services.auth.main import app
from shared.database import Base, get_db
from shared.models.user import User, OAuthAccount


# 创建测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_oauth.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建表
Base.metadata.create_all(bind=engine)


def override_get_db():
    """覆盖数据库依赖"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_and_teardown():
    """每个测试前后的设置和清理"""
    # 清理数据库
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # 测试后清理
    Base.metadata.drop_all(bind=engine)


class TestOAuthAuthentication:
    """OAuth认证测试"""
    
    @patch('shared.utils.oauth_client.GoogleOAuthClient.exchange_code_for_token')
    @patch('shared.utils.oauth_client.GoogleOAuthClient.get_user_info')
    @patch('shared.redis_client.get_redis')
    def test_oauth_new_user_registration(self, mock_redis, mock_get_user_info, mock_exchange_token):
        """测试OAuth新用户注册"""
        # Mock OAuth响应
        mock_exchange_token.return_value = {
            "access_token": "google_access_token_123",
            "refresh_token": "google_refresh_token_123",
            "expires_in": 3600,
            "id_token": "google_id_token_123"
        }
        
        mock_get_user_info.return_value = {
            "provider_user_id": "google_user_12345",
            "username": "testuser",
            "email": "testuser@gmail.com",
            "avatar": "https://example.com/avatar.jpg",
            "extra": {
                "name": "Test User",
                "email_verified": True
            }
        }
        
        # Mock Redis
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance
        
        # 发送OAuth认证请求
        response = client.post(
            "/api/v1/auth/oauth/google",
            json={
                "code": "google_auth_code_123",
                "redirect_uri": "http://localhost:3000/callback"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 验证响应
        assert "access_token" in data
        assert "refresh_token" in data
        assert "sso_session_token" in data
        assert data["token_type"] == "Bearer"
        assert data["is_new_user"] is True
        assert data["user"]["username"] == "testuser"
        assert data["user"]["email"] == "testuser@gmail.com"
        
        # 验证数据库中创建了用户
        db = TestingSessionLocal()
        user = db.query(User).filter(User.email == "testuser@gmail.com").first()
        assert user is not None
        assert user.username == "testuser"
        assert user.status == "active"
        
        # 验证创建了OAuth账号关联
        oauth_account = db.query(OAuthAccount).filter(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_user_id == "google_user_12345"
        ).first()
        assert oauth_account is not None
        assert oauth_account.user_id == user.id
        assert oauth_account.access_token == "google_access_token_123"
        
        db.close()
    
    @patch('shared.utils.oauth_client.GoogleOAuthClient.exchange_code_for_token')
    @patch('shared.utils.oauth_client.GoogleOAuthClient.get_user_info')
    @patch('shared.redis_client.get_redis')
    def test_oauth_existing_user_login(self, mock_redis, mock_get_user_info, mock_exchange_token):
        """测试OAuth已存在用户登录"""
        # 先创建用户和OAuth账号
        db = TestingSessionLocal()
        user = User(
            username="existinguser",
            email="existing@gmail.com",
            status="active"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        oauth_account = OAuthAccount(
            user_id=user.id,
            provider="google",
            provider_user_id="google_user_existing",
            access_token="old_token",
            refresh_token="old_refresh"
        )
        db.add(oauth_account)
        db.commit()
        db.close()
        
        # Mock OAuth响应
        mock_exchange_token.return_value = {
            "access_token": "new_google_token",
            "refresh_token": "new_google_refresh",
            "expires_in": 3600
        }
        
        mock_get_user_info.return_value = {
            "provider_user_id": "google_user_existing",
            "username": "existinguser",
            "email": "existing@gmail.com"
        }
        
        # Mock Redis
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance
        
        # 发送OAuth认证请求
        response = client.post(
            "/api/v1/auth/oauth/google",
            json={
                "code": "google_auth_code_456",
                "redirect_uri": "http://localhost:3000/callback"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 验证响应
        assert data["is_new_user"] is False
        assert data["user"]["username"] == "existinguser"
        
        # 验证OAuth令牌已更新
        db = TestingSessionLocal()
        oauth_account = db.query(OAuthAccount).filter(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_user_id == "google_user_existing"
        ).first()
        assert oauth_account.access_token == "new_google_token"
        assert oauth_account.refresh_token == "new_google_refresh"
        db.close()
    
    @patch('shared.utils.oauth_client.GoogleOAuthClient.exchange_code_for_token')
    @patch('shared.utils.oauth_client.GoogleOAuthClient.get_user_info')
    @patch('shared.redis_client.get_redis')
    def test_oauth_email_account_linking(self, mock_redis, mock_get_user_info, mock_exchange_token):
        """测试OAuth通过邮箱关联现有账号"""
        # 先创建一个邮箱注册的用户（没有OAuth账号）
        db = TestingSessionLocal()
        user = User(
            username="emailuser",
            email="emailuser@gmail.com",
            password_hash="hashed_password",
            status="active"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        db.close()
        
        # Mock OAuth响应（返回相同邮箱）
        mock_exchange_token.return_value = {
            "access_token": "google_token",
            "refresh_token": "google_refresh",
            "expires_in": 3600
        }
        
        mock_get_user_info.return_value = {
            "provider_user_id": "google_user_link",
            "username": "googleuser",
            "email": "emailuser@gmail.com"  # 相同邮箱
        }
        
        # Mock Redis
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance
        
        # 发送OAuth认证请求
        response = client.post(
            "/api/v1/auth/oauth/google",
            json={
                "code": "google_auth_code_link",
                "redirect_uri": "http://localhost:3000/callback"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 验证关联到现有用户（不是新用户）
        assert data["is_new_user"] is False
        assert data["user"]["username"] == "emailuser"  # 保持原用户名
        assert data["user"]["email"] == "emailuser@gmail.com"
        
        # 验证OAuth账号关联到现有用户
        db = TestingSessionLocal()
        oauth_account = db.query(OAuthAccount).filter(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_user_id == "google_user_link"
        ).first()
        assert oauth_account is not None
        assert oauth_account.user_id == user_id
        
        # 验证没有创建新用户
        user_count = db.query(User).filter(User.email == "emailuser@gmail.com").count()
        assert user_count == 1
        
        db.close()
    
    @patch('shared.utils.oauth_client.WeChatOAuthClient.exchange_code_for_token')
    @patch('shared.utils.oauth_client.WeChatOAuthClient.get_user_info')
    @patch('shared.redis_client.get_redis')
    def test_wechat_oauth(self, mock_redis, mock_get_user_info, mock_exchange_token):
        """测试微信OAuth认证"""
        mock_exchange_token.return_value = {
            "access_token": "wechat_token",
            "refresh_token": "wechat_refresh",
            "expires_in": 7200,
            "openid": "wechat_openid_123"
        }
        
        mock_get_user_info.return_value = {
            "provider_user_id": "wechat_openid_123",
            "username": "微信用户",
            "avatar": "https://wx.qlogo.cn/avatar.jpg"
        }
        
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance
        
        response = client.post(
            "/api/v1/auth/oauth/wechat",
            json={
                "code": "wechat_code",
                "redirect_uri": "http://localhost:3000/callback"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_new_user"] is True
        assert "微信用户" in data["user"]["username"]
    
    @patch('shared.utils.oauth_client.AlipayOAuthClient.exchange_code_for_token')
    @patch('shared.utils.oauth_client.AlipayOAuthClient.get_user_info')
    @patch('shared.redis_client.get_redis')
    def test_alipay_oauth(self, mock_redis, mock_get_user_info, mock_exchange_token):
        """测试支付宝OAuth认证"""
        mock_exchange_token.return_value = {
            "access_token": "alipay_token",
            "refresh_token": "alipay_refresh",
            "expires_in": 86400,
            "user_id": "alipay_user_123"
        }
        
        mock_get_user_info.return_value = {
            "provider_user_id": "alipay_user_123",
            "username": "支付宝用户",
            "avatar": "https://alipay.com/avatar.jpg"
        }
        
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance
        
        response = client.post(
            "/api/v1/auth/oauth/alipay",
            json={
                "code": "alipay_code",
                "redirect_uri": "http://localhost:3000/callback"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_new_user"] is True
        assert "支付宝用户" in data["user"]["username"]
    
    @patch('shared.utils.oauth_client.AppleOAuthClient.exchange_code_for_token')
    @patch('shared.utils.oauth_client.AppleOAuthClient.get_user_info')
    @patch('shared.redis_client.get_redis')
    def test_apple_oauth(self, mock_redis, mock_get_user_info, mock_exchange_token):
        """测试Apple OAuth认证"""
        mock_exchange_token.return_value = {
            "access_token": "apple_token",
            "refresh_token": "apple_refresh",
            "expires_in": 3600,
            "id_token": "apple_id_token"
        }
        
        mock_get_user_info.return_value = {
            "provider_user_id": "apple_user_123",
            "username": "apple_user",
            "email": "user@privaterelay.appleid.com"
        }
        
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance
        
        response = client.post(
            "/api/v1/auth/oauth/apple",
            json={
                "code": "apple_code",
                "redirect_uri": "http://localhost:3000/callback"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_new_user"] is True
        assert data["user"]["email"] == "user@privaterelay.appleid.com"
    
    def test_oauth_unsupported_provider(self):
        """测试不支持的OAuth提供商"""
        response = client.post(
            "/api/v1/auth/oauth/facebook",
            json={
                "code": "some_code",
                "redirect_uri": "http://localhost:3000/callback"
            }
        )
        
        assert response.status_code == 400
        assert "不支持的OAuth提供商" in response.json()["detail"]
    
    @patch('shared.utils.oauth_client.GoogleOAuthClient.exchange_code_for_token')
    @patch('shared.redis_client.get_redis')
    def test_oauth_token_exchange_failure(self, mock_redis, mock_exchange_token):
        """测试OAuth令牌交换失败"""
        # Mock令牌交换失败
        mock_exchange_token.side_effect = Exception("Invalid authorization code")
        
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance
        
        response = client.post(
            "/api/v1/auth/oauth/google",
            json={
                "code": "invalid_code",
                "redirect_uri": "http://localhost:3000/callback"
            }
        )
        
        assert response.status_code == 500
        assert "OAuth认证失败" in response.json()["detail"]
    
    @patch('shared.utils.oauth_client.GoogleOAuthClient.exchange_code_for_token')
    @patch('shared.utils.oauth_client.GoogleOAuthClient.get_user_info')
    @patch('shared.redis_client.get_redis')
    def test_oauth_duplicate_username_handling(self, mock_redis, mock_get_user_info, mock_exchange_token):
        """测试OAuth用户名冲突处理"""
        # 先创建一个用户占用用户名
        db = TestingSessionLocal()
        existing_user = User(
            username="testuser",
            email="other@example.com",
            status="active"
        )
        db.add(existing_user)
        db.commit()
        db.close()
        
        # Mock OAuth响应（返回相同用户名但不同邮箱）
        mock_exchange_token.return_value = {
            "access_token": "google_token",
            "refresh_token": "google_refresh",
            "expires_in": 3600
        }
        
        mock_get_user_info.return_value = {
            "provider_user_id": "google_user_dup",
            "username": "testuser",  # 相同用户名
            "email": "newuser@gmail.com"  # 不同邮箱
        }
        
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance
        
        response = client.post(
            "/api/v1/auth/oauth/google",
            json={
                "code": "google_code",
                "redirect_uri": "http://localhost:3000/callback"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 验证生成了新的用户名（添加了后缀）
        assert data["user"]["username"] != "testuser"
        assert data["user"]["username"].startswith("testuser_")
        
        # 验证创建了新用户
        db = TestingSessionLocal()
        new_user = db.query(User).filter(User.email == "newuser@gmail.com").first()
        assert new_user is not None
        assert new_user.username.startswith("testuser_")
        db.close()
    
    def test_oauth_get_authorization_url(self):
        """测试获取OAuth授权URL"""
        response = client.get(
            "/api/v1/auth/oauth/google/authorize",
            params={
                "redirect_uri": "http://localhost:3000/callback",
                "state": "random_state_123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "authorization_url" in data
        assert "state" in data
        assert "accounts.google.com" in data["authorization_url"]
        assert data["state"] == "random_state_123"
    
    def test_oauth_get_authorization_url_without_state(self):
        """测试获取OAuth授权URL（不提供state）"""
        response = client.get(
            "/api/v1/auth/oauth/google/authorize",
            params={
                "redirect_uri": "http://localhost:3000/callback"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "authorization_url" in data
        assert "state" in data
        assert len(data["state"]) > 0  # 自动生成的state


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
