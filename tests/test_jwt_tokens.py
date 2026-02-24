"""
JWT Token生成测试

Feature: unified-auth-platform, Property 4: 登录Token生成

对于任意认证方式（邮箱、手机、OAuth），当用户成功登录时，
系统应该返回有效的Access Token和Refresh Token，且两个Token都能通过签名验证。

验证需求：1.4
"""
import pytest
from datetime import datetime, timedelta
from hypothesis import given, strategies as st
from shared.utils.jwt import create_access_token, create_refresh_token, decode_token
from shared.config import settings


# 用户ID生成器（UUID字符串）
user_ids = st.uuids().map(str)

# 用户名生成器
usernames = st.text(
    alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')),
    min_size=3,
    max_size=50
)

# 邮箱生成器
emails = st.emails()

# 角色列表生成器
roles = st.lists(
    st.sampled_from(['user', 'admin', 'moderator', 'viewer']),
    min_size=1,
    max_size=3,
    unique=True
)

# 权限列表生成器
permissions = st.lists(
    st.sampled_from([
        'user:read', 'user:create', 'user:update', 'user:delete',
        'role:read', 'role:create', 'role:update', 'role:delete'
    ]),
    min_size=0,
    max_size=5,
    unique=True
)


@given(
    user_id=user_ids,
    username=usernames,
    email=emails,
    user_roles=roles,
    user_permissions=permissions
)
def test_token_generation_integrity(user_id, username, email, user_roles, user_permissions):
    """
    属性 4：登录Token生成
    
    对于任意用户数据，当生成Token时应该：
    1. 成功生成Access Token和Refresh Token
    2. 两个Token都能通过签名验证
    3. Token包含正确的用户信息
    4. Token有正确的过期时间
    """
    # 准备Token载荷数据
    token_data = {
        "sub": user_id,
        "username": username,
        "email": email,
        "roles": user_roles,
        "permissions": user_permissions
    }
    
    # 生成Access Token
    access_token = create_access_token(token_data)
    
    # 生成Refresh Token
    refresh_token_data = {
        "sub": user_id,
        "token_id": str(st.uuids().example())
    }
    refresh_token = create_refresh_token(refresh_token_data)
    
    # 属性1：Token应该是非空字符串
    assert isinstance(access_token, str), "Access Token应该是字符串"
    assert len(access_token) > 0, "Access Token不应该为空"
    assert isinstance(refresh_token, str), "Refresh Token应该是字符串"
    assert len(refresh_token) > 0, "Refresh Token不应该为空"
    
    # 属性2：Token应该能够解码和验证
    decoded_access = decode_token(access_token)
    decoded_refresh = decode_token(refresh_token)
    
    assert decoded_access is not None, "Access Token应该能够成功解码"
    assert decoded_refresh is not None, "Refresh Token应该能够成功解码"
    
    # 属性3：Access Token应该包含正确的用户信息
    assert decoded_access["sub"] == user_id, "Access Token应该包含正确的用户ID"
    assert decoded_access["username"] == username, "Access Token应该包含正确的用户名"
    assert decoded_access["email"] == email, "Access Token应该包含正确的邮箱"
    assert decoded_access["roles"] == user_roles, "Access Token应该包含正确的角色"
    assert decoded_access["permissions"] == user_permissions, "Access Token应该包含正确的权限"
    
    # 属性4：Refresh Token应该包含正确的用户ID
    assert decoded_refresh["sub"] == user_id, "Refresh Token应该包含正确的用户ID"
    
    # 属性5：Token应该包含必要的JWT标准字段
    assert "exp" in decoded_access, "Access Token应该包含过期时间"
    assert "iat" in decoded_access, "Access Token应该包含签发时间"
    assert "iss" in decoded_access, "Access Token应该包含签发者"
    
    assert "exp" in decoded_refresh, "Refresh Token应该包含过期时间"
    assert "iat" in decoded_refresh, "Refresh Token应该包含签发时间"
    assert "iss" in decoded_refresh, "Refresh Token应该包含签发者"
    
    # 属性6：签发者应该是正确的应用名称
    assert decoded_access["iss"] == settings.APP_NAME, "Access Token签发者应该正确"
    assert decoded_refresh["iss"] == settings.APP_NAME, "Refresh Token签发者应该正确"
    
    # 属性7：过期时间应该在合理范围内
    now = datetime.utcnow()
    access_exp = datetime.fromtimestamp(decoded_access["exp"])
    refresh_exp = datetime.fromtimestamp(decoded_refresh["exp"])
    
    # Access Token应该在15分钟后过期（允许1分钟误差）
    expected_access_exp = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    assert abs((access_exp - expected_access_exp).total_seconds()) < 60, \
        "Access Token过期时间应该在15分钟左右"
    
    # Refresh Token应该在14天后过期（允许1小时误差）
    expected_refresh_exp = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    assert abs((refresh_exp - expected_refresh_exp).total_seconds()) < 3600, \
        "Refresh Token过期时间应该在14天左右"
    
    # 属性8：签发时间应该是当前时间（允许1分钟误差）
    access_iat = datetime.fromtimestamp(decoded_access["iat"])
    refresh_iat = datetime.fromtimestamp(decoded_refresh["iat"])
    
    assert abs((access_iat - now).total_seconds()) < 60, \
        "Access Token签发时间应该是当前时间"
    assert abs((refresh_iat - now).total_seconds()) < 60, \
        "Refresh Token签发时间应该是当前时间"


def test_token_generation_with_specific_examples():
    """使用具体示例测试Token生成"""
    test_cases = [
        {
            "sub": "123e4567-e89b-12d3-a456-426614174000",
            "username": "johndoe",
            "email": "john@example.com",
            "roles": ["user"],
            "permissions": ["user:read"]
        },
        {
            "sub": "987fcdeb-51a2-43f7-8b6d-6c9f8e7d6c5b",
            "username": "admin",
            "email": "admin@example.com",
            "roles": ["admin", "user"],
            "permissions": ["user:read", "user:create", "user:update", "user:delete"]
        },
        {
            "sub": "456789ab-cdef-0123-4567-89abcdef0123",
            "username": "viewer",
            "email": "viewer@example.com",
            "roles": ["viewer"],
            "permissions": []
        }
    ]
    
    for token_data in test_cases:
        # 生成Token
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token({"sub": token_data["sub"], "token_id": "test-token-id"})
        
        # 验证Token
        decoded_access = decode_token(access_token)
        decoded_refresh = decode_token(refresh_token)
        
        assert decoded_access is not None, f"应该能解码Access Token: {token_data['username']}"
        assert decoded_refresh is not None, f"应该能解码Refresh Token: {token_data['username']}"
        
        # 验证数据
        assert decoded_access["sub"] == token_data["sub"]
        assert decoded_access["username"] == token_data["username"]
        assert decoded_access["email"] == token_data["email"]
        assert decoded_refresh["sub"] == token_data["sub"]


def test_token_with_custom_expiration():
    """测试自定义过期时间的Token"""
    token_data = {
        "sub": "test-user-id",
        "username": "testuser",
        "email": "test@example.com"
    }
    
    # 创建5分钟过期的Token
    custom_expires = timedelta(minutes=5)
    access_token = create_access_token(token_data, expires_delta=custom_expires)
    
    decoded = decode_token(access_token)
    assert decoded is not None, "应该能解码自定义过期时间的Token"
    
    # 验证过期时间
    now = datetime.utcnow()
    exp = datetime.fromtimestamp(decoded["exp"])
    expected_exp = now + custom_expires
    
    assert abs((exp - expected_exp).total_seconds()) < 60, \
        "自定义过期时间应该正确设置"


def test_token_signature_verification():
    """测试Token签名验证"""
    token_data = {
        "sub": "test-user-id",
        "username": "testuser",
        "email": "test@example.com"
    }
    
    # 生成Token
    access_token = create_access_token(token_data)
    
    # 正确的Token应该能验证
    decoded = decode_token(access_token)
    assert decoded is not None, "正确的Token应该能验证"
    
    # 篡改Token应该验证失败
    tampered_token = access_token[:-10] + "tampered123"
    decoded_tampered = decode_token(tampered_token)
    assert decoded_tampered is None, "篡改的Token应该验证失败"
    
    # 无效格式的Token应该验证失败
    invalid_token = "invalid.token.format"
    decoded_invalid = decode_token(invalid_token)
    assert decoded_invalid is None, "无效格式的Token应该验证失败"


def test_token_uniqueness():
    """测试Token唯一性"""
    token_data = {
        "sub": "test-user-id",
        "username": "testuser",
        "email": "test@example.com"
    }
    
    # 生成多个Token
    tokens = [create_access_token(token_data) for _ in range(10)]
    
    # 所有Token应该不同（因为签发时间不同）
    unique_tokens = set(tokens)
    assert len(unique_tokens) == len(tokens), \
        "多次生成的Token应该不同（因为签发时间不同）"


def test_empty_roles_and_permissions():
    """测试空角色和权限"""
    token_data = {
        "sub": "test-user-id",
        "username": "testuser",
        "email": "test@example.com",
        "roles": [],
        "permissions": []
    }
    
    access_token = create_access_token(token_data)
    decoded = decode_token(access_token)
    
    assert decoded is not None, "应该能生成空角色和权限的Token"
    assert decoded["roles"] == [], "应该正确保存空角色列表"
    assert decoded["permissions"] == [], "应该正确保存空权限列表"


def test_token_with_minimal_data():
    """测试最小数据的Token"""
    # 只包含必需的sub字段
    minimal_data = {"sub": "test-user-id"}
    
    access_token = create_access_token(minimal_data)
    refresh_token = create_refresh_token(minimal_data)
    
    decoded_access = decode_token(access_token)
    decoded_refresh = decode_token(refresh_token)
    
    assert decoded_access is not None, "应该能生成最小数据的Access Token"
    assert decoded_refresh is not None, "应该能生成最小数据的Refresh Token"
    assert decoded_access["sub"] == "test-user-id"
    assert decoded_refresh["sub"] == "test-user-id"


@given(user_id=user_ids)
def test_refresh_token_minimal_payload(user_id):
    """
    测试Refresh Token的最小载荷
    
    Refresh Token应该只包含必要的信息（用户ID和token_id），
    不应该包含敏感的用户详细信息
    """
    refresh_data = {
        "sub": user_id,
        "token_id": str(st.uuids().example())
    }
    
    refresh_token = create_refresh_token(refresh_data)
    decoded = decode_token(refresh_token)
    
    assert decoded is not None, "Refresh Token应该能成功解码"
    assert decoded["sub"] == user_id, "Refresh Token应该包含用户ID"
    assert "token_id" in decoded, "Refresh Token应该包含token_id"
    
    # Refresh Token不应该包含详细的用户信息
    # （这是一个安全最佳实践，因为Refresh Token有效期更长）
    assert "username" not in refresh_data, "Refresh Token不应该包含用户名"
    assert "email" not in refresh_data, "Refresh Token不应该包含邮箱"
    assert "roles" not in refresh_data, "Refresh Token不应该包含角色"
    assert "permissions" not in refresh_data, "Refresh Token不应该包含权限"
