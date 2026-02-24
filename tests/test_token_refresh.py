"""
Token刷新测试

Feature: unified-auth-platform, Property 5: Token刷新往返

对于任意有效的Refresh Token，当Access Token过期后使用Refresh Token刷新时，
系统应该返回新的Access Token，且新Token能够成功验证用户身份。

验证需求：1.5
"""
import pytest
import time
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, assume
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


@given(
    user_id=user_ids,
    username=usernames,
    email=emails
)
def test_token_refresh_roundtrip(user_id, username, email):
    """
    属性 5：Token刷新往返
    
    对于任意有效的Refresh Token，应该能够：
    1. 使用Refresh Token生成新的Access Token
    2. 新的Access Token能够成功解码
    3. 新的Access Token包含正确的用户信息
    4. 刷新过程保持用户身份一致
    """
    # 创建初始Token
    initial_token_data = {
        "sub": user_id,
        "username": username,
        "email": email
    }
    
    initial_access_token = create_access_token(initial_token_data)
    refresh_token = create_refresh_token({"sub": user_id})
    
    # 属性1：初始Token应该有效
    initial_decoded = decode_token(initial_access_token)
    assert initial_decoded is not None, "初始Access Token应该有效"
    assert initial_decoded["sub"] == user_id, "初始Token应该包含正确的用户ID"
    
    # 属性2：Refresh Token应该有效
    refresh_decoded = decode_token(refresh_token)
    assert refresh_decoded is not None, "Refresh Token应该有效"
    assert refresh_decoded["sub"] == user_id, "Refresh Token应该包含正确的用户ID"
    
    # 模拟Token刷新流程
    # 从Refresh Token中提取用户ID
    refresh_payload = decode_token(refresh_token)
    assert refresh_payload is not None, "应该能解码Refresh Token"
    
    # 使用用户ID生成新的Access Token
    new_token_data = {
        "sub": refresh_payload["sub"],
        "username": username,
        "email": email
    }
    new_access_token = create_access_token(new_token_data)
    
    # 属性3：新的Access Token应该有效
    new_decoded = decode_token(new_access_token)
    assert new_decoded is not None, "新的Access Token应该有效"
    
    # 属性4：新Token应该包含正确的用户信息
    assert new_decoded["sub"] == user_id, "新Token应该包含正确的用户ID"
    assert new_decoded["username"] == username, "新Token应该包含正确的用户名"
    assert new_decoded["email"] == email, "新Token应该包含正确的邮箱"
    
    # 属性5：新旧Token的用户身份应该一致
    assert initial_decoded["sub"] == new_decoded["sub"], \
        "刷新前后的用户ID应该一致"
    
    # 属性6：新Token应该有新的签发时间
    assert new_decoded["iat"] >= initial_decoded["iat"], \
        "新Token的签发时间应该晚于或等于初始Token"
    
    # 属性7：新Token应该有新的过期时间
    assert new_decoded["exp"] >= initial_decoded["exp"], \
        "新Token的过期时间应该晚于或等于初始Token"


@given(user_id=user_ids)
def test_refresh_token_validity_period(user_id):
    """
    测试Refresh Token的有效期
    
    Refresh Token应该在有效期内可用，过期后不可用
    """
    # 创建Refresh Token
    refresh_token = create_refresh_token({"sub": user_id})
    
    # 立即解码应该成功
    decoded = decode_token(refresh_token)
    assert decoded is not None, "新创建的Refresh Token应该有效"
    assert decoded["sub"] == user_id, "应该包含正确的用户ID"
    
    # 验证过期时间设置正确（14天）
    exp_time = datetime.fromtimestamp(decoded["exp"])
    now = datetime.utcnow()
    expected_exp = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    # 允许1小时的误差
    time_diff = abs((exp_time - expected_exp).total_seconds())
    assert time_diff < 3600, "Refresh Token过期时间应该设置为14天"


@given(user_id=user_ids)
def test_multiple_refresh_cycles(user_id):
    """
    测试多次刷新周期
    
    应该能够多次使用Refresh Token刷新Access Token
    """
    # 创建初始Refresh Token
    refresh_token = create_refresh_token({"sub": user_id})
    
    # 模拟多次刷新
    previous_tokens = []
    for i in range(5):
        # 验证Refresh Token
        refresh_payload = decode_token(refresh_token)
        assert refresh_payload is not None, f"第{i+1}次刷新时Refresh Token应该有效"
        
        # 生成新的Access Token
        new_access_token = create_access_token({"sub": refresh_payload["sub"]})
        previous_tokens.append(new_access_token)
        
        # 验证新Token
        new_decoded = decode_token(new_access_token)
        assert new_decoded is not None, f"第{i+1}次刷新生成的Access Token应该有效"
        assert new_decoded["sub"] == user_id, f"第{i+1}次刷新后用户ID应该一致"
        
        # 短暂延迟以确保时间戳不同
        time.sleep(0.01)
    
    # 所有生成的Token都应该有效
    for idx, token in enumerate(previous_tokens):
        decoded = decode_token(token)
        assert decoded is not None, f"第{idx+1}个Token应该仍然有效"
        assert decoded["sub"] == user_id, f"第{idx+1}个Token的用户ID应该正确"


def test_refresh_token_with_expired_access_token():
    """
    测试Access Token过期后使用Refresh Token刷新
    """
    user_id = "test-user-123"
    
    # 创建一个很短有效期的Access Token（1秒）
    short_lived_token = create_access_token(
        {"sub": user_id},
        expires_delta=timedelta(seconds=1)
    )
    
    # 创建正常的Refresh Token
    refresh_token = create_refresh_token({"sub": user_id})
    
    # 立即验证Access Token应该有效
    decoded = decode_token(short_lived_token)
    assert decoded is not None, "新创建的Access Token应该有效"
    
    # 等待Access Token过期
    time.sleep(2)
    
    # Access Token应该已过期
    expired_decoded = decode_token(short_lived_token)
    assert expired_decoded is None, "过期的Access Token应该无效"
    
    # 但Refresh Token应该仍然有效
    refresh_decoded = decode_token(refresh_token)
    assert refresh_decoded is not None, "Refresh Token应该仍然有效"
    
    # 使用Refresh Token生成新的Access Token
    new_access_token = create_access_token({"sub": refresh_decoded["sub"]})
    new_decoded = decode_token(new_access_token)
    
    assert new_decoded is not None, "新生成的Access Token应该有效"
    assert new_decoded["sub"] == user_id, "新Token应该包含正确的用户ID"


def test_refresh_token_independence():
    """
    测试Refresh Token的独立性
    
    每个用户的Refresh Token应该独立，不能用于刷新其他用户的Token
    """
    user1_id = "user-1"
    user2_id = "user-2"
    
    # 为两个用户创建Refresh Token
    refresh_token_1 = create_refresh_token({"sub": user1_id})
    refresh_token_2 = create_refresh_token({"sub": user2_id})
    
    # 解码两个Refresh Token
    decoded_1 = decode_token(refresh_token_1)
    decoded_2 = decode_token(refresh_token_2)
    
    assert decoded_1 is not None, "用户1的Refresh Token应该有效"
    assert decoded_2 is not None, "用户2的Refresh Token应该有效"
    
    # 使用用户1的Refresh Token生成Access Token
    new_token_1 = create_access_token({"sub": decoded_1["sub"]})
    new_decoded_1 = decode_token(new_token_1)
    
    # 使用用户2的Refresh Token生成Access Token
    new_token_2 = create_access_token({"sub": decoded_2["sub"]})
    new_decoded_2 = decode_token(new_token_2)
    
    # 验证用户身份独立
    assert new_decoded_1["sub"] == user1_id, "用户1的新Token应该包含用户1的ID"
    assert new_decoded_2["sub"] == user2_id, "用户2的新Token应该包含用户2的ID"
    assert new_decoded_1["sub"] != new_decoded_2["sub"], "两个用户的Token应该不同"


def test_refresh_with_invalid_token():
    """
    测试使用无效的Refresh Token刷新
    """
    # 无效的Token格式
    invalid_tokens = [
        "invalid.token.format",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature",
        "",
        "not-a-jwt-token",
        "a" * 100
    ]
    
    for invalid_token in invalid_tokens:
        decoded = decode_token(invalid_token)
        assert decoded is None, f"无效的Token应该解码失败: {invalid_token[:20]}..."


def test_refresh_token_contains_minimal_info():
    """
    测试Refresh Token只包含最小必要信息
    
    这是一个安全最佳实践：Refresh Token有效期长，
    应该只包含必要信息，不包含敏感的用户详细信息
    """
    user_id = "test-user-123"
    
    # 创建Refresh Token（只包含用户ID）
    refresh_token = create_refresh_token({"sub": user_id})
    decoded = decode_token(refresh_token)
    
    assert decoded is not None, "Refresh Token应该有效"
    assert "sub" in decoded, "Refresh Token应该包含用户ID"
    
    # Refresh Token不应该包含详细的用户信息
    # （这些信息应该只在Access Token中）
    assert "username" not in decoded, "Refresh Token不应该包含用户名"
    assert "email" not in decoded, "Refresh Token不应该包含邮箱"
    assert "roles" not in decoded, "Refresh Token不应该包含角色"
    assert "permissions" not in decoded, "Refresh Token不应该包含权限"


@given(user_id=user_ids)
def test_refresh_preserves_user_identity(user_id):
    """
    测试刷新过程保持用户身份
    
    无论刷新多少次，用户身份应该始终保持一致
    """
    # 创建Refresh Token
    refresh_token = create_refresh_token({"sub": user_id})
    
    # 多次刷新并验证用户身份
    for _ in range(10):
        refresh_payload = decode_token(refresh_token)
        assert refresh_payload is not None, "Refresh Token应该有效"
        
        # 生成新的Access Token
        new_access_token = create_access_token({"sub": refresh_payload["sub"]})
        new_decoded = decode_token(new_access_token)
        
        # 验证用户身份一致
        assert new_decoded is not None, "新Access Token应该有效"
        assert new_decoded["sub"] == user_id, "用户身份应该保持一致"
        assert refresh_payload["sub"] == user_id, "Refresh Token的用户ID应该一致"


def test_refresh_token_rotation_simulation():
    """
    模拟Refresh Token轮换策略
    
    在实际应用中，每次刷新时应该生成新的Refresh Token
    这个测试模拟这个过程
    """
    user_id = "test-user-123"
    
    # 初始Refresh Token
    current_refresh_token = create_refresh_token({"sub": user_id})
    
    # 模拟3次刷新周期
    for cycle in range(3):
        # 验证当前Refresh Token
        refresh_payload = decode_token(current_refresh_token)
        assert refresh_payload is not None, f"第{cycle+1}周期的Refresh Token应该有效"
        
        # 生成新的Access Token
        new_access_token = create_access_token({"sub": refresh_payload["sub"]})
        new_access_decoded = decode_token(new_access_token)
        assert new_access_decoded is not None, f"第{cycle+1}周期的Access Token应该有效"
        
        # 生成新的Refresh Token（轮换）
        new_refresh_token = create_refresh_token({"sub": user_id})
        new_refresh_decoded = decode_token(new_refresh_token)
        assert new_refresh_decoded is not None, f"第{cycle+1}周期的新Refresh Token应该有效"
        
        # 验证用户身份一致
        assert new_access_decoded["sub"] == user_id, "Access Token用户ID应该一致"
        assert new_refresh_decoded["sub"] == user_id, "Refresh Token用户ID应该一致"
        
        # 更新当前Refresh Token
        current_refresh_token = new_refresh_token
        
        time.sleep(0.01)


def test_concurrent_refresh_requests():
    """
    测试并发刷新请求
    
    同一个Refresh Token应该能够处理多个并发的刷新请求
    """
    user_id = "test-user-123"
    refresh_token = create_refresh_token({"sub": user_id})
    
    # 模拟多个并发请求
    new_tokens = []
    for _ in range(5):
        refresh_payload = decode_token(refresh_token)
        assert refresh_payload is not None, "Refresh Token应该有效"
        
        new_access_token = create_access_token({"sub": refresh_payload["sub"]})
        new_tokens.append(new_access_token)
    
    # 所有新生成的Token都应该有效
    for idx, token in enumerate(new_tokens):
        decoded = decode_token(token)
        assert decoded is not None, f"第{idx+1}个并发生成的Token应该有效"
        assert decoded["sub"] == user_id, f"第{idx+1}个Token的用户ID应该正确"


def test_refresh_after_access_token_expiry():
    """
    测试Access Token过期后的完整刷新流程
    """
    user_id = "test-user-123"
    username = "testuser"
    email = "test@example.com"
    
    # 步骤1：初始登录，生成Token
    initial_access_token = create_access_token({
        "sub": user_id,
        "username": username,
        "email": email
    }, expires_delta=timedelta(seconds=1))
    
    refresh_token = create_refresh_token({"sub": user_id})
    
    # 步骤2：验证初始Token有效
    initial_decoded = decode_token(initial_access_token)
    assert initial_decoded is not None, "初始Access Token应该有效"
    assert initial_decoded["sub"] == user_id
    
    # 步骤3：等待Access Token过期
    time.sleep(2)
    
    # 步骤4：验证Access Token已过期
    expired_decoded = decode_token(initial_access_token)
    assert expired_decoded is None, "Access Token应该已过期"
    
    # 步骤5：使用Refresh Token获取新的Access Token
    refresh_payload = decode_token(refresh_token)
    assert refresh_payload is not None, "Refresh Token应该仍然有效"
    
    new_access_token = create_access_token({
        "sub": refresh_payload["sub"],
        "username": username,
        "email": email
    })
    
    # 步骤6：验证新Token有效且包含正确信息
    new_decoded = decode_token(new_access_token)
    assert new_decoded is not None, "新Access Token应该有效"
    assert new_decoded["sub"] == user_id, "用户ID应该一致"
    assert new_decoded["username"] == username, "用户名应该一致"
    assert new_decoded["email"] == email, "邮箱应该一致"
