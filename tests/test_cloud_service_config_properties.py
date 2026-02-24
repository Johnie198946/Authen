"""
云服务配置验证属性测试

测试任务 14.3：编写云服务配置验证属性测试
- **属性 27：云服务配置验证**
- 验证需求：8.5

**Validates: Requirements 8.5**

属性 27：对于任意云服务配置（邮件或短信），当管理员保存配置时，
系统应该验证配置的有效性（如SMTP连接、API密钥有效性），无效配置应该被拒绝。

使用Hypothesis进行基于属性的测试，验证配置验证逻辑在各种输入下的正确性。
"""
import pytest
import sys
import os
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from unittest.mock import patch, MagicMock
import smtplib

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.admin.main import (
    validate_smtp_config,
    validate_aliyun_sms_config,
    validate_tencent_sms_config,
    validate_cloud_service_config
)


# ==================== 测试数据生成策略 ====================

# SMTP配置生成器
@st.composite
def smtp_configs(draw, valid=True):
    """
    生成SMTP配置
    
    Args:
        valid: 是否生成有效配置
    """
    if valid:
        # 生成有效的SMTP配置
        config = {
            "smtp_host": draw(st.text(
                alphabet=st.characters(whitelist_categories=('Ll', 'Nd'), whitelist_characters='.-'),
                min_size=5,
                max_size=50
            )),
            "smtp_port": draw(st.integers(min_value=1, max_value=65535)),
            "username": draw(st.emails()),
            "password": draw(st.text(min_size=8, max_size=32)),
            "use_ssl": draw(st.booleans())
        }
    else:
        # 生成无效的SMTP配置（缺少字段或无效值）
        choice = draw(st.integers(min_value=0, max_value=3))
        
        if choice == 0:
            # 缺少必需字段
            config = {
                "smtp_host": draw(st.text(min_size=5, max_size=50)),
                # 缺少其他必需字段
            }
        elif choice == 1:
            # 无效端口号
            config = {
                "smtp_host": draw(st.text(min_size=5, max_size=50)),
                "smtp_port": draw(st.one_of(
                    st.integers(max_value=0),
                    st.integers(min_value=65536),
                    st.text()
                )),
                "username": draw(st.emails()),
                "password": draw(st.text(min_size=8, max_size=32))
            }
        elif choice == 2:
            # 空字段
            config = {
                "smtp_host": "",
                "smtp_port": 465,
                "username": "",
                "password": ""
            }
        else:
            # 缺少部分必需字段
            config = {
                "smtp_host": draw(st.text(min_size=5, max_size=50)),
                "smtp_port": draw(st.integers(min_value=1, max_value=65535)),
                # 缺少username和password
            }
    
    return config


# 阿里云短信配置生成器
@st.composite
def aliyun_sms_configs(draw, valid=True):
    """
    生成阿里云短信配置
    
    Args:
        valid: 是否生成有效配置
    """
    if valid:
        # 生成有效的阿里云短信配置
        config = {
            "access_key_id": draw(st.text(
                alphabet=st.characters(whitelist_categories=('Lu', 'Nd')),
                min_size=16,
                max_size=32
            )),
            "access_key_secret": draw(st.text(
                alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')),
                min_size=24,
                max_size=48
            )),
            "sign_name": draw(st.text(
                alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_'),
                min_size=2,
                max_size=20
            ))
        }
    else:
        # 生成无效的阿里云短信配置
        choice = draw(st.integers(min_value=0, max_value=2))
        
        if choice == 0:
            # 缺少必需字段
            config = {
                "access_key_id": draw(st.text(min_size=16, max_size=32)),
                # 缺少其他必需字段
            }
        elif choice == 1:
            # 空字段
            config = {
                "access_key_id": "",
                "access_key_secret": "",
                "sign_name": ""
            }
        else:
            # 缺少部分必需字段
            config = {
                "access_key_id": draw(st.text(min_size=16, max_size=32)),
                "access_key_secret": draw(st.text(min_size=24, max_size=48)),
                # 缺少sign_name
            }
    
    return config


# 腾讯云短信配置生成器
@st.composite
def tencent_sms_configs(draw, valid=True):
    """
    生成腾讯云短信配置
    
    Args:
        valid: 是否生成有效配置
    """
    if valid:
        # 生成有效的腾讯云短信配置
        config = {
            "secret_id": draw(st.text(
                alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')),
                min_size=32,
                max_size=64
            )),
            "secret_key": draw(st.text(
                alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')),
                min_size=32,
                max_size=64
            )),
            "sdk_app_id": draw(st.text(
                alphabet=st.characters(whitelist_categories=('Nd')),
                min_size=10,
                max_size=12
            )),
            "sign_name": draw(st.text(
                alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_'),
                min_size=2,
                max_size=20
            ))
        }
    else:
        # 生成无效的腾讯云短信配置
        choice = draw(st.integers(min_value=0, max_value=2))
        
        if choice == 0:
            # 缺少必需字段
            config = {
                "secret_id": draw(st.text(min_size=32, max_size=64)),
                # 缺少其他必需字段
            }
        elif choice == 1:
            # 空字段
            config = {
                "secret_id": "",
                "secret_key": "",
                "sdk_app_id": "",
                "sign_name": ""
            }
        else:
            # 缺少部分必需字段
            config = {
                "secret_id": draw(st.text(min_size=32, max_size=64)),
                "secret_key": draw(st.text(min_size=32, max_size=64)),
                # 缺少sdk_app_id和sign_name
            }
    
    return config


# ==================== 属性测试 ====================

class TestProperty27_CloudServiceConfigValidation:
    """
    属性 27：云服务配置验证
    
    **Validates: Requirements 8.5**
    
    对于任意云服务配置（邮件或短信），当管理员保存配置时，
    系统应该验证配置的有效性（如SMTP连接、API密钥有效性），
    无效配置应该被拒绝。
    """
    
    @given(config=smtp_configs(valid=False))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_property_27_invalid_smtp_configs_rejected(self, config):
        """
        属性测试：无效的SMTP配置应该被拒绝
        
        对于任意无效的SMTP配置（缺少必需字段、无效端口等），
        验证函数应该返回False并提供错误消息。
        """
        is_valid, error_msg = validate_smtp_config(config)
        
        # 无效配置应该被拒绝
        assert not is_valid, f"无效配置应该被拒绝，但返回了有效: {config}"
        assert error_msg, "应该提供错误消息"
        assert isinstance(error_msg, str), "错误消息应该是字符串"
        assert len(error_msg) > 0, "错误消息不应该为空"
    
    @given(config=smtp_configs(valid=True))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @patch('smtplib.SMTP_SSL')
    @patch('smtplib.SMTP')
    def test_property_27_valid_smtp_configs_structure(self, mock_smtp, mock_smtp_ssl, config):
        """
        属性测试：有效的SMTP配置应该通过结构验证
        
        对于任意结构有效的SMTP配置（包含所有必需字段且格式正确），
        验证函数应该尝试连接SMTP服务器。
        """
        # Mock SMTP服务器成功连接
        mock_server = MagicMock()
        mock_smtp_ssl.return_value = mock_server
        mock_smtp.return_value = mock_server
        
        is_valid, error_msg = validate_smtp_config(config)
        
        # 应该尝试连接（调用了SMTP或SMTP_SSL）
        assert mock_smtp_ssl.called or mock_smtp.called, "应该尝试连接SMTP服务器"
        
        # 如果连接成功，应该返回有效
        if not mock_server.login.side_effect:
            assert is_valid, f"有效配置应该通过验证: {error_msg}"
    
    @given(config=aliyun_sms_configs(valid=False))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_property_27_invalid_aliyun_sms_configs_rejected(self, config):
        """
        属性测试：无效的阿里云短信配置应该被拒绝
        
        对于任意无效的阿里云短信配置（缺少必需字段、空字段等），
        验证函数应该返回False并提供错误消息。
        """
        is_valid, error_msg = validate_aliyun_sms_config(config)
        
        # 无效配置应该被拒绝
        assert not is_valid, f"无效配置应该被拒绝，但返回了有效: {config}"
        assert error_msg, "应该提供错误消息"
        assert isinstance(error_msg, str), "错误消息应该是字符串"
        assert len(error_msg) > 0, "错误消息不应该为空"
    
    @given(config=tencent_sms_configs(valid=False))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_property_27_invalid_tencent_sms_configs_rejected(self, config):
        """
        属性测试：无效的腾讯云短信配置应该被拒绝
        
        对于任意无效的腾讯云短信配置（缺少必需字段、空字段等），
        验证函数应该返回False并提供错误消息。
        """
        is_valid, error_msg = validate_tencent_sms_config(config)
        
        # 无效配置应该被拒绝
        assert not is_valid, f"无效配置应该被拒绝，但返回了有效: {config}"
        assert error_msg, "应该提供错误消息"
        assert isinstance(error_msg, str), "错误消息应该是字符串"
        assert len(error_msg) > 0, "错误消息不应该为空"
    
    @given(
        service_type=st.sampled_from(['email', 'sms']),
        provider=st.sampled_from(['aliyun', 'tencent', 'aws']),
        config=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.text(), st.integers(), st.booleans())
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_property_27_validation_always_returns_tuple(self, service_type, provider, config):
        """
        属性测试：验证函数总是返回(bool, str)元组
        
        对于任意服务类型、提供商和配置，验证函数应该总是返回
        一个包含布尔值和字符串的元组。
        """
        result = validate_cloud_service_config(service_type, provider, config)
        
        # 应该返回元组
        assert isinstance(result, tuple), "验证函数应该返回元组"
        assert len(result) == 2, "元组应该包含两个元素"
        
        is_valid, error_msg = result
        
        # 第一个元素应该是布尔值
        assert isinstance(is_valid, bool), "第一个元素应该是布尔值"
        
        # 第二个元素应该是字符串
        assert isinstance(error_msg, str), "第二个元素应该是字符串"
        assert len(error_msg) > 0, "错误消息不应该为空"
    
    @given(
        port=st.one_of(
            st.integers(max_value=0),
            st.integers(min_value=65536, max_value=100000)
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_property_27_smtp_port_validation(self, port):
        """
        属性测试：SMTP端口号验证
        
        对于任意超出有效范围(1-65535)的端口号，
        验证函数应该拒绝配置。
        """
        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": port,
            "username": "test@example.com",
            "password": "password123"
        }
        
        is_valid, error_msg = validate_smtp_config(config)
        
        # 无效端口应该被拒绝
        assert not is_valid, f"无效端口 {port} 应该被拒绝"
        assert "端口" in error_msg or "port" in error_msg.lower(), "错误消息应该提到端口"
    
    @given(
        missing_field=st.sampled_from(['smtp_host', 'smtp_port', 'username', 'password'])
    )
    @settings(max_examples=50, deadline=None)
    def test_property_27_smtp_missing_required_fields(self, missing_field):
        """
        属性测试：SMTP缺少必需字段
        
        对于任意缺少必需字段的SMTP配置，
        验证函数应该拒绝配置并指出缺少的字段。
        """
        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "username": "test@example.com",
            "password": "password123"
        }
        
        # 删除指定字段
        del config[missing_field]
        
        is_valid, error_msg = validate_smtp_config(config)
        
        # 缺少必需字段应该被拒绝
        assert not is_valid, f"缺少 {missing_field} 的配置应该被拒绝"
        assert "缺少" in error_msg or "missing" in error_msg.lower(), "错误消息应该提到缺少字段"
    
    @given(
        missing_field=st.sampled_from(['access_key_id', 'access_key_secret', 'sign_name'])
    )
    @settings(max_examples=50, deadline=None)
    def test_property_27_aliyun_missing_required_fields(self, missing_field):
        """
        属性测试：阿里云短信缺少必需字段
        
        对于任意缺少必需字段的阿里云短信配置，
        验证函数应该拒绝配置并指出缺少的字段。
        """
        config = {
            "access_key_id": "LTAI5tTest123456",
            "access_key_secret": "TestSecret123456789",
            "sign_name": "TestSign"
        }
        
        # 删除指定字段
        del config[missing_field]
        
        is_valid, error_msg = validate_aliyun_sms_config(config)
        
        # 缺少必需字段应该被拒绝
        assert not is_valid, f"缺少 {missing_field} 的配置应该被拒绝"
        assert "缺少" in error_msg or "missing" in error_msg.lower(), "错误消息应该提到缺少字段"
    
    @given(
        missing_field=st.sampled_from(['secret_id', 'secret_key', 'sdk_app_id', 'sign_name'])
    )
    @settings(max_examples=50, deadline=None)
    def test_property_27_tencent_missing_required_fields(self, missing_field):
        """
        属性测试：腾讯云短信缺少必需字段
        
        对于任意缺少必需字段的腾讯云短信配置，
        验证函数应该拒绝配置并指出缺少的字段。
        """
        config = {
            "secret_id": "AKIDTest123456789012345678901234",
            "secret_key": "TestKey123456789012345678901234",
            "sdk_app_id": "1400000000",
            "sign_name": "TestSign"
        }
        
        # 删除指定字段
        del config[missing_field]
        
        is_valid, error_msg = validate_tencent_sms_config(config)
        
        # 缺少必需字段应该被拒绝
        assert not is_valid, f"缺少 {missing_field} 的配置应该被拒绝"
        assert "缺少" in error_msg or "missing" in error_msg.lower(), "错误消息应该提到缺少字段"
    
    @given(
        provider=st.text(
            alphabet=st.characters(whitelist_categories=('Ll',)),
            min_size=3,
            max_size=20
        ).filter(lambda x: x not in ['aliyun', 'tencent', 'aws'])
    )
    @settings(max_examples=50, deadline=None)
    def test_property_27_unsupported_sms_provider_rejected(self, provider):
        """
        属性测试：不支持的短信服务提供商应该被拒绝
        
        对于任意不支持的短信服务提供商，
        验证函数应该返回False并提供错误消息。
        """
        config = {
            "api_key": "test_key",
            "api_secret": "test_secret"
        }
        
        is_valid, error_msg = validate_cloud_service_config('sms', provider, config)
        
        # 不支持的提供商应该被拒绝
        assert not is_valid, f"不支持的提供商 {provider} 应该被拒绝"
        assert "不支持" in error_msg or "unsupported" in error_msg.lower(), "错误消息应该提到不支持"
    
    @given(
        service_type=st.text(
            alphabet=st.characters(whitelist_categories=('Ll',)),
            min_size=3,
            max_size=20
        ).filter(lambda x: x not in ['email', 'sms'])
    )
    @settings(max_examples=50, deadline=None)
    def test_property_27_unsupported_service_type_rejected(self, service_type):
        """
        属性测试：不支持的服务类型应该被拒绝
        
        对于任意不支持的服务类型，
        验证函数应该返回False并提供错误消息。
        """
        config = {
            "test_field": "test_value"
        }
        
        is_valid, error_msg = validate_cloud_service_config(service_type, 'aliyun', config)
        
        # 不支持的服务类型应该被拒绝
        assert not is_valid, f"不支持的服务类型 {service_type} 应该被拒绝"
        assert "不支持" in error_msg or "unsupported" in error_msg.lower(), "错误消息应该提到不支持"
    
    @given(config=smtp_configs(valid=True))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @patch('smtplib.SMTP')
    @patch('smtplib.SMTP_SSL')
    def test_property_27_smtp_connection_failure_rejected(self, mock_smtp_ssl, mock_smtp, config):
        """
        属性测试：SMTP连接失败应该被拒绝
        
        对于任意结构有效的SMTP配置，如果无法连接到服务器，
        验证函数应该返回False并提供错误消息。
        """
        # Mock连接失败（同时mock SSL和非SSL）
        mock_smtp_ssl.side_effect = smtplib.SMTPConnectError(421, b"Service not available")
        mock_smtp.side_effect = smtplib.SMTPConnectError(421, b"Service not available")
        
        is_valid, error_msg = validate_smtp_config(config)
        
        # 连接失败应该被拒绝
        assert not is_valid, "连接失败的配置应该被拒绝"
        # 错误消息可能包含"连接"、"connect"或其他连接相关的词
        error_msg_lower = error_msg.lower()
        assert any(word in error_msg_lower for word in ["连接", "connect", "无法", "failed", "refused", "timeout"]), \
            f"错误消息应该提到连接问题，但得到: {error_msg}"
    
    @given(config=smtp_configs(valid=True))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @patch('smtplib.SMTP')
    @patch('smtplib.SMTP_SSL')
    def test_property_27_smtp_auth_failure_rejected(self, mock_smtp_ssl, mock_smtp, config):
        """
        属性测试：SMTP认证失败应该被拒绝
        
        对于任意结构有效的SMTP配置，如果认证失败，
        验证函数应该返回False并提供错误消息。
        """
        # Mock认证失败（同时mock SSL和非SSL）
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
        mock_smtp_ssl.return_value = mock_server
        mock_smtp.return_value = mock_server
        
        is_valid, error_msg = validate_smtp_config(config)
        
        # 认证失败应该被拒绝
        assert not is_valid, "认证失败的配置应该被拒绝"
        # 错误消息可能包含"认证"、"auth"或其他认证相关的词
        error_msg_lower = error_msg.lower()
        assert any(word in error_msg_lower for word in ["认证", "auth", "login", "failed", "refused", "连接"]), \
            f"错误消息应该提到认证或连接问题，但得到: {error_msg}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
