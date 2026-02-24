"""
SQL注入防护属性测试

需求：11.3 - 验证SQL注入防护机制

使用Property-Based Testing验证系统能够正确防御SQL注入攻击
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from shared.utils.security import (
    sanitize_sql_input,
    validate_sql_safe,
    sanitize_order_by,
    sanitize_like_pattern
)


# ==================== 测试策略 ====================

# SQL注入攻击向量
sql_injection_vectors = st.sampled_from([
    "' OR '1'='1",
    "'; DROP TABLE users--",
    "1' UNION SELECT * FROM users--",
    "admin'--",
    "' OR 1=1--",
    "1; DELETE FROM users",
    "' UNION SELECT NULL, NULL--",
    "1' AND '1'='1",
    "'; EXEC xp_cmdshell('dir')--",
    "1' OR '1'='1' /*",
    "admin' OR '1'='1' #",
    "' OR 'x'='x",
    "1'; DROP TABLE users; --",
    "' UNION ALL SELECT NULL--",
    "admin' AND 1=1--",
])

# 安全的输入
safe_inputs = st.one_of(
    st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')), min_size=1, max_size=50),
    st.from_regex(r'^[a-zA-Z0-9_]+$', fullmatch=True),
    st.integers(min_value=1, max_value=1000000).map(str),
)

# 列名策略
column_names = st.sampled_from([
    'id', 'username', 'email', 'created_at', 'updated_at',
    'name', 'status', 'role', 'phone', 'address'
])


# ==================== 属性30：SQL注入防护 ====================

@given(sql_injection_vectors)
@settings(max_examples=100, deadline=None)
def test_sql_property_detect_injection_attempts(injection_vector):
    """
    属性30.1：检测SQL注入尝试
    
    **验证需求：11.3**
    
    属性：对于任何SQL注入攻击向量，validate_sql_safe应该返回False
    
    Args:
        injection_vector: SQL注入攻击向量
    """
    is_safe, error_msg = validate_sql_safe(injection_vector)
    
    # 验证：应该检测到SQL注入风险
    assert not is_safe, f"未检测到SQL注入: {injection_vector}"
    assert error_msg is not None, "应该返回错误消息"
    assert "不安全" in error_msg or "SQL" in error_msg


@given(sql_injection_vectors)
@settings(max_examples=100, deadline=None)
def test_sql_property_sanitize_removes_dangerous_content(injection_vector):
    """
    属性30.2：清理移除危险内容
    
    **验证需求：11.3**
    
    属性：对于任何SQL注入向量，sanitize_sql_input应该移除或转义危险内容
    
    Args:
        injection_vector: SQL注入攻击向量
    """
    sanitized = sanitize_sql_input(injection_vector)
    
    # 验证：清理后的内容不应包含SQL关键字
    dangerous_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'UNION', 'EXEC']
    for keyword in dangerous_keywords:
        assert keyword.upper() not in sanitized.upper(), \
            f"清理后仍包含危险关键字 {keyword}: {sanitized}"


@given(safe_inputs)
@settings(max_examples=100, deadline=None)
def test_sql_property_safe_inputs_pass_validation(safe_input):
    """
    属性30.3：安全输入通过验证
    
    **验证需求：11.3**
    
    属性：对于安全的输入，validate_sql_safe应该返回True
    
    Args:
        safe_input: 安全的输入字符串
    """
    # 假设：输入不包含SQL关键字
    assume(not any(keyword in safe_input.upper() for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP']))
    
    is_safe, error_msg = validate_sql_safe(safe_input)
    
    # 验证：安全输入应该通过验证
    assert is_safe, f"安全输入未通过验证: {safe_input}, 错误: {error_msg}"
    assert error_msg is None


@given(safe_inputs)
@settings(max_examples=100, deadline=None)
def test_sql_property_sanitize_preserves_safe_content(safe_input):
    """
    属性30.4：清理保留安全内容
    
    **验证需求：11.3**
    
    属性：对于安全的输入，sanitize_sql_input应该保留原始内容
    
    Args:
        safe_input: 安全的输入字符串
    """
    # 假设：输入不包含SQL关键字和特殊字符
    assume(not any(keyword in safe_input.upper() for keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP']))
    assume('--' not in safe_input and ';' not in safe_input)
    
    sanitized = sanitize_sql_input(safe_input)
    
    # 验证：安全内容应该被保留
    assert sanitized == safe_input, f"安全内容被修改: {safe_input} -> {sanitized}"


@given(column_names, st.lists(column_names, min_size=1, max_size=10))
@settings(max_examples=100, deadline=None)
def test_sql_property_order_by_whitelist(column, allowed_columns):
    """
    属性30.5：ORDER BY白名单验证
    
    **验证需求：11.3**
    
    属性：只有在白名单中的列名才能通过ORDER BY验证
    
    Args:
        column: 列名
        allowed_columns: 允许的列名列表
    """
    if column in allowed_columns:
        # 在白名单中，应该通过
        result = sanitize_order_by(column, allowed_columns)
        assert result == column
    else:
        # 不在白名单中，应该抛出异常
        with pytest.raises(ValueError, match="不允许的排序列"):
            sanitize_order_by(column, allowed_columns)


@given(st.text(min_size=1, max_size=50))
@settings(max_examples=100, deadline=None)
def test_sql_property_order_by_rejects_injection(malicious_column):
    """
    属性30.6：ORDER BY拒绝注入
    
    **验证需求：11.3**
    
    属性：包含特殊字符的列名应该被拒绝
    
    Args:
        malicious_column: 可能包含恶意内容的列名
    """
    # 假设：列名包含特殊字符
    assume(any(char in malicious_column for char in [';', '--', ' ', '(', ')', '*']))
    
    allowed_columns = ['id', 'username', 'email']
    
    # 验证：应该抛出异常
    with pytest.raises(ValueError):
        sanitize_order_by(malicious_column, allowed_columns)


@given(st.text(min_size=1, max_size=100))
@settings(max_examples=100, deadline=None)
def test_sql_property_like_pattern_escapes_wildcards(pattern):
    """
    属性30.7：LIKE模式转义通配符
    
    **验证需求：11.3**
    
    属性：LIKE模式中的通配符应该被正确转义
    
    Args:
        pattern: LIKE模式
    """
    sanitized = sanitize_like_pattern(pattern)
    
    # 验证：通配符应该被转义
    if '%' in pattern:
        assert '\\%' in sanitized or '%' not in sanitized
    if '_' in pattern:
        assert '\\_' in sanitized or '_' not in sanitized


@given(st.text(alphabet=st.characters(blacklist_characters='%_[]\\'), min_size=1, max_size=50))
@settings(max_examples=100, deadline=None)
def test_sql_property_like_pattern_preserves_normal_chars(pattern):
    """
    属性30.8：LIKE模式保留普通字符
    
    **验证需求：11.3**
    
    属性：不包含特殊字符的模式应该被保留
    
    Args:
        pattern: 不包含特殊字符的模式
    """
    sanitized = sanitize_like_pattern(pattern)
    
    # 验证：普通字符应该被保留
    # 注意：反斜杠会被转义
    assert pattern in sanitized or pattern.replace('\\', '\\\\') == sanitized


# ==================== 边界测试 ====================

def test_sql_property_empty_input():
    """
    边界测试：空输入
    
    验证空字符串的处理
    """
    # 空字符串应该是安全的
    is_safe, error_msg = validate_sql_safe("")
    assert is_safe
    assert error_msg is None
    
    # 清理空字符串应该返回空字符串
    assert sanitize_sql_input("") == ""


def test_sql_property_none_input():
    """
    边界测试：None输入
    
    验证None值的处理
    """
    # None应该是安全的
    is_safe, error_msg = validate_sql_safe(None)
    assert is_safe
    
    # 清理None应该返回None
    assert sanitize_sql_input(None) is None


def test_sql_property_numeric_input():
    """
    边界测试：数字输入
    
    验证数字类型的处理
    """
    # 数字应该是安全的
    is_safe, error_msg = validate_sql_safe(123)
    assert is_safe
    
    # 清理数字应该返回原值
    assert sanitize_sql_input(123) == 123


def test_sql_property_very_long_input():
    """
    边界测试：超长输入
    
    验证超长字符串的处理
    """
    long_input = "a" * 10000
    
    # 应该能处理超长输入
    is_safe, error_msg = validate_sql_safe(long_input)
    assert is_safe
    
    sanitized = sanitize_sql_input(long_input)
    assert len(sanitized) <= len(long_input)


# ==================== 组合测试 ====================

@given(
    st.text(min_size=1, max_size=50),
    st.sampled_from(['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP'])
)
@settings(max_examples=100, deadline=None)
def test_sql_property_mixed_safe_and_dangerous(safe_part, dangerous_keyword):
    """
    组合测试：混合安全和危险内容
    
    **验证需求：11.3**
    
    属性：包含SQL关键字的输入应该被检测或清理
    
    Args:
        safe_part: 安全的部分
        dangerous_keyword: 危险的SQL关键字
    """
    # 假设：安全部分不包含SQL关键字
    assume(not any(kw in safe_part.upper() for kw in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP']))
    
    mixed_input = f"{safe_part} {dangerous_keyword}"
    
    # 验证：应该检测到危险内容
    is_safe, error_msg = validate_sql_safe(mixed_input)
    assert not is_safe, f"未检测到危险内容: {mixed_input}"
    
    # 清理后应该移除危险关键字
    sanitized = sanitize_sql_input(mixed_input)
    assert dangerous_keyword.upper() not in sanitized.upper()


# ==================== 性能测试 ====================

@given(st.lists(st.text(min_size=1, max_size=100), min_size=10, max_size=100))
@settings(max_examples=10, deadline=None)
def test_sql_property_batch_validation_performance(inputs):
    """
    性能测试：批量验证
    
    验证批量输入验证的性能
    
    Args:
        inputs: 输入列表
    """
    # 批量验证应该能快速完成
    results = [validate_sql_safe(inp) for inp in inputs]
    
    # 验证：所有输入都应该被处理
    assert len(results) == len(inputs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
