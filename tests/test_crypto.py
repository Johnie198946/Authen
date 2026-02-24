"""
密码加密测试

Feature: unified-auth-platform, Property 7: 密码加密存储

对于任意用户密码，存储到数据库中的值应该是经过bcrypt或类似算法加密的哈希值，
且原始密码不应该能从哈希值中恢复。

验证需求：1.7
"""
import pytest
from hypothesis import given, strategies as st
from shared.utils.crypto import hash_password, verify_password


# 密码生成器（符合复杂度要求）
passwords = st.text(
    alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters='!@#$%^&*()'
    ),
    min_size=8,
    max_size=32
)


@given(password=passwords)
def test_password_encryption_integrity(password):
    """
    属性 7：密码加密存储
    
    对于任意有效密码，加密后的哈希值应该：
    1. 不等于原始密码
    2. 能够通过验证函数验证
    3. 不能从哈希值恢复原始密码
    """
    # 加密密码
    hashed = hash_password(password)
    
    # 属性1：哈希值不等于原始密码
    assert hashed != password, "密码哈希值不应该等于原始密码"
    
    # 属性2：哈希值应该能够验证原始密码
    assert verify_password(password, hashed), "应该能够验证正确的密码"
    
    # 属性3：错误的密码不应该通过验证
    wrong_password = password + "wrong"
    assert not verify_password(wrong_password, hashed), "错误的密码不应该通过验证"
    
    # 属性4：哈希值应该是字符串且长度合理（bcrypt哈希长度为60）
    assert isinstance(hashed, str), "哈希值应该是字符串"
    assert len(hashed) == 60, "bcrypt哈希值长度应该是60"
    
    # 属性5：相同密码的多次加密应该产生不同的哈希值（因为有盐值）
    hashed2 = hash_password(password)
    assert hashed != hashed2, "相同密码的多次加密应该产生不同的哈希值"
    
    # 属性6：两个不同的哈希值都应该能验证原始密码
    assert verify_password(password, hashed2), "第二个哈希值也应该能验证原始密码"


def test_password_encryption_with_specific_examples():
    """使用具体示例测试密码加密"""
    test_cases = [
        "Password123!",
        "SecurePass456@",
        "MyP@ssw0rd",
        "Test1234!@#$"
    ]
    
    for password in test_cases:
        hashed = hash_password(password)
        
        # 验证正确密码
        assert verify_password(password, hashed), f"应该能验证密码: {password}"
        
        # 验证错误密码
        assert not verify_password(password + "x", hashed), f"不应该验证错误密码: {password}x"
        assert not verify_password("", hashed), "不应该验证空密码"


def test_empty_password_handling():
    """测试空密码处理"""
    # 空密码也应该能够加密（虽然不推荐）
    hashed = hash_password("")
    assert verify_password("", hashed), "应该能验证空密码"
    assert not verify_password("a", hashed), "不应该验证非空密码"


def test_special_characters_in_password():
    """测试特殊字符密码"""
    special_passwords = [
        "P@ssw0rd!",
        "Test#123$",
        "My%Pass^123",
        "Secure&Pass*456"
    ]
    
    for password in special_passwords:
        hashed = hash_password(password)
        assert verify_password(password, hashed), f"应该能验证包含特殊字符的密码: {password}"
