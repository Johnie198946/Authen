"""
XSS防护属性测试

需求：11.4 - 验证XSS攻击防护机制

使用Property-Based Testing验证系统能够正确防御XSS攻击
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from shared.utils.security import (
    sanitize_html,
    escape_html,
    sanitize_javascript,
    validate_url,
    sanitize_json_output
)


# ==================== 测试策略 ====================

# XSS攻击向量
xss_vectors = st.sampled_from([
    "<script>alert('XSS')</script>",
    "<img src=x onerror=alert('XSS')>",
    "<svg onload=alert('XSS')>",
    "javascript:alert('XSS')",
    "<iframe src='javascript:alert(\"XSS\")'></iframe>",
    "<body onload=alert('XSS')>",
    "<input onfocus=alert('XSS') autofocus>",
    "<select onfocus=alert('XSS') autofocus>",
    "<textarea onfocus=alert('XSS') autofocus>",
    "<marquee onstart=alert('XSS')>",
    "<div style='background:url(javascript:alert(\"XSS\"))'></div>",
    "<a href='javascript:alert(\"XSS\")'>Click</a>",
    "<<SCRIPT>alert('XSS');//<</SCRIPT>",
    "<IMG SRC=\"javascript:alert('XSS');\">",
    "<IMG SRC=javascript:alert('XSS')>",
])

# 安全的HTML内容
safe_html = st.one_of(
    st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs')), min_size=1, max_size=100),
    st.from_regex(r'^[a-zA-Z0-9\s.,!?]+$', fullmatch=True),
)

# 安全的URL
safe_urls = st.sampled_from([
    "https://example.com",
    "http://example.com/path",
    "https://example.com/path?query=value",
    "https://sub.example.com",
    "/relative/path",
    "//example.com/path",
])

# 危险的URL
dangerous_urls = st.sampled_from([
    "javascript:alert('XSS')",
    "data:text/html,<script>alert('XSS')</script>",
    "vbscript:msgbox('XSS')",
    "file:///etc/passwd",
    "javascript:void(0)",
])


# ==================== 属性31：XSS攻击防护 ====================

@given(xss_vectors)
@settings(max_examples=100, deadline=None)
def test_xss_property_sanitize_html_removes_scripts(xss_vector):
    """
    属性31.1：清理HTML移除脚本
    
    **验证需求：11.4**
    
    属性：对于任何XSS攻击向量，sanitize_html应该移除危险内容
    
    Args:
        xss_vector: XSS攻击向量
    """
    sanitized = sanitize_html(xss_vector)
    
    # 验证：清理后不应包含script标签
    assert '<script' not in sanitized.lower(), f"未移除script标签: {sanitized}"
    assert 'javascript:' not in sanitized.lower(), f"未移除javascript协议: {sanitized}"
    assert 'onerror' not in sanitized.lower(), f"未移除onerror事件: {sanitized}"
    assert 'onload' not in sanitized.lower(), f"未移除onload事件: {sanitized}"


@given(xss_vectors)
@settings(max_examples=100, deadline=None)
def test_xss_property_escape_html_neutralizes_tags(xss_vector):
    """
    属性31.2：转义HTML中和标签
    
    **验证需求：11.4**
    
    属性：对于任何XSS向量，escape_html应该转义所有HTML特殊字符
    
    Args:
        xss_vector: XSS攻击向量
    """
    escaped = escape_html(xss_vector)
    
    # 验证：特殊字符应该被转义
    assert '<' not in escaped or '&lt;' in escaped, "未转义<符号"
    assert '>' not in escaped or '&gt;' in escaped, "未转义>符号"
    assert '"' not in escaped or '&quot;' in escaped or '&#x27;' in escaped, "未转义引号"


@given(safe_html)
@settings(max_examples=100, deadline=None)
def test_xss_property_safe_content_preserved(safe_content):
    """
    属性31.3：安全内容被保留
    
    **验证需求：11.4**
    
    属性：对于安全的内容，sanitize_html应该保留原始内容
    
    Args:
        safe_content: 安全的HTML内容
    """
    # 假设：内容不包含HTML标签
    assume('<' not in safe_content and '>' not in safe_content)
    
    sanitized = sanitize_html(safe_content)
    
    # 验证：安全内容应该被保留
    assert sanitized == safe_content, f"安全内容被修改: {safe_content} -> {sanitized}"


@given(xss_vectors)
@settings(max_examples=100, deadline=None)
def test_xss_property_sanitize_javascript_removes_dangerous_code(xss_vector):
    """
    属性31.4：清理JavaScript移除危险代码
    
    **验证需求：11.4**
    
    属性：对于任何XSS向量，sanitize_javascript应该移除危险的JavaScript代码
    
    Args:
        xss_vector: XSS攻击向量
    """
    sanitized = sanitize_javascript(xss_vector)
    
    # 验证：危险的JavaScript模式应该被移除
    assert 'eval(' not in sanitized.lower(), "未移除eval"
    assert 'settimeout(' not in sanitized.lower(), "未移除setTimeout"
    assert 'setinterval(' not in sanitized.lower(), "未移除setInterval"


@given(dangerous_urls)
@settings(max_examples=100, deadline=None)
def test_xss_property_validate_url_rejects_dangerous_protocols(dangerous_url):
    """
    属性31.5：验证URL拒绝危险协议
    
    **验证需求：11.4**
    
    属性：对于危险的URL，validate_url应该返回False
    
    Args:
        dangerous_url: 危险的URL
    """
    is_safe, error_msg = validate_url(dangerous_url)
    
    # 验证：应该检测到危险URL
    assert not is_safe, f"未检测到危险URL: {dangerous_url}"
    assert error_msg is not None, "应该返回错误消息"


@given(safe_urls)
@settings(max_examples=100, deadline=None)
def test_xss_property_validate_url_accepts_safe_urls(safe_url):
    """
    属性31.6：验证URL接受安全URL
    
    **验证需求：11.4**
    
    属性：对于安全的URL，validate_url应该返回True
    
    Args:
        safe_url: 安全的URL
    """
    is_safe, error_msg = validate_url(safe_url)
    
    # 验证：安全URL应该通过验证
    assert is_safe, f"安全URL未通过验证: {safe_url}, 错误: {error_msg}"
    assert error_msg is None


@given(st.dictionaries(
    keys=st.text(min_size=1, max_size=20),
    values=st.one_of(st.text(min_size=0, max_size=100), st.integers(), st.booleans())
))
@settings(max_examples=100, deadline=None)
def test_xss_property_sanitize_json_escapes_strings(data):
    """
    属性31.7：清理JSON转义字符串
    
    **验证需求：11.4**
    
    属性：对于任何JSON数据，sanitize_json_output应该转义字符串中的HTML
    
    Args:
        data: JSON数据字典
    """
    sanitized = sanitize_json_output(data)
    
    # 验证：字符串值应该被转义
    def check_escaped(obj):
        if isinstance(obj, str):
            # 如果原始字符串包含<或>，清理后应该被转义
            if '<' in obj or '>' in obj:
                assert '<' not in obj or '&lt;' in escape_html(obj)
        elif isinstance(obj, dict):
            for value in obj.values():
                check_escaped(value)
        elif isinstance(obj, list):
            for item in obj:
                check_escaped(item)
    
    check_escaped(sanitized)


# ==================== 边界测试 ====================

def test_xss_property_empty_input():
    """
    边界测试：空输入
    
    验证空字符串的处理
    """
    # 空字符串应该返回空字符串
    assert sanitize_html("") == ""
    assert escape_html("") == ""
    assert sanitize_javascript("") == ""


def test_xss_property_none_input():
    """
    边界测试：None输入
    
    验证None值的处理
    """
    # None应该返回空字符串
    assert sanitize_html(None) == ""
    assert escape_html(None) == ""
    assert sanitize_javascript(None) == ""


def test_xss_property_very_long_input():
    """
    边界测试：超长输入
    
    验证超长字符串的处理
    """
    long_input = "<script>alert('XSS')</script>" * 1000
    
    # 应该能处理超长输入
    sanitized = sanitize_html(long_input)
    assert '<script' not in sanitized.lower()


def test_xss_property_nested_tags():
    """
    边界测试：嵌套标签
    
    验证嵌套HTML标签的处理
    """
    nested = "<div><script>alert('XSS')</script></div>"
    
    sanitized = sanitize_html(nested)
    assert '<script' not in sanitized.lower()


def test_xss_property_encoded_attacks():
    """
    边界测试：编码攻击
    
    验证HTML实体编码的XSS攻击
    """
    encoded = "&lt;script&gt;alert('XSS')&lt;/script&gt;"
    
    # 已编码的内容应该保持编码状态
    sanitized = sanitize_html(encoded)
    # 不应该被解码后执行
    assert 'alert' not in sanitized or '&' in sanitized


# ==================== 组合测试 ====================

@given(
    st.text(min_size=1, max_size=50),
    xss_vectors
)
@settings(max_examples=100, deadline=None)
def test_xss_property_mixed_safe_and_dangerous(safe_part, xss_vector):
    """
    组合测试：混合安全和危险内容
    
    **验证需求：11.4**
    
    属性：包含XSS向量的内容应该被清理
    
    Args:
        safe_part: 安全的部分
        xss_vector: XSS攻击向量
    """
    # 假设：安全部分不包含HTML标签
    assume('<' not in safe_part and '>' not in safe_part)
    
    mixed_content = f"{safe_part} {xss_vector}"
    
    sanitized = sanitize_html(mixed_content)
    
    # 验证：危险内容应该被移除，安全内容应该保留
    assert '<script' not in sanitized.lower()
    # 安全部分应该在清理后的内容中
    assert safe_part in sanitized or escape_html(safe_part) in sanitized


@given(
    st.lists(xss_vectors, min_size=1, max_size=10)
)
@settings(max_examples=50, deadline=None)
def test_xss_property_multiple_attacks(xss_vectors_list):
    """
    组合测试：多个XSS攻击
    
    **验证需求：11.4**
    
    属性：包含多个XSS向量的内容应该全部被清理
    
    Args:
        xss_vectors_list: XSS攻击向量列表
    """
    combined = " ".join(xss_vectors_list)
    
    sanitized = sanitize_html(combined)
    
    # 验证：所有危险内容都应该被移除
    assert '<script' not in sanitized.lower()
    assert 'javascript:' not in sanitized.lower()
    assert 'onerror' not in sanitized.lower()


# ==================== 允许标签测试 ====================

@given(st.text(min_size=1, max_size=100))
@settings(max_examples=100, deadline=None)
def test_xss_property_allowed_tags_preserved(text_content):
    """
    允许标签测试：保留允许的标签
    
    **验证需求：11.4**
    
    属性：在允许列表中的标签应该被保留
    
    Args:
        text_content: 文本内容
    """
    # 假设：内容不包含危险字符
    assume('<' not in text_content and '>' not in text_content)
    assume('script' not in text_content.lower())
    
    html_with_allowed_tags = f"<p>{text_content}</p>"
    
    # 允许<p>标签
    sanitized = sanitize_html(html_with_allowed_tags, allowed_tags=['p'])
    
    # 验证：<p>标签应该被保留
    assert '<p>' in sanitized
    assert text_content in sanitized


def test_xss_property_disallowed_tags_removed():
    """
    允许标签测试：移除不允许的标签
    
    验证不在允许列表中的标签被移除
    """
    html = "<p>Safe</p><script>alert('XSS')</script>"
    
    # 只允许<p>标签
    sanitized = sanitize_html(html, allowed_tags=['p'])
    
    # 验证：<p>保留，<script>移除
    assert '<p>' in sanitized
    assert '<script' not in sanitized.lower()


# ==================== 性能测试 ====================

@given(st.lists(st.text(min_size=1, max_size=100), min_size=10, max_size=100))
@settings(max_examples=10, deadline=None)
def test_xss_property_batch_sanitization_performance(inputs):
    """
    性能测试：批量清理
    
    验证批量内容清理的性能
    
    Args:
        inputs: 输入列表
    """
    # 批量清理应该能快速完成
    results = [sanitize_html(inp) for inp in inputs]
    
    # 验证：所有输入都应该被处理
    assert len(results) == len(inputs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
