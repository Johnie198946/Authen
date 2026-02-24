"""
云服务配置验证测试

测试任务 14.2：实现配置验证功能
- 实现SMTP配置验证
- 实现短信API配置验证
- 验证需求：8.5
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock
import smtplib

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.admin.main import (
    validate_smtp_config,
    validate_aliyun_sms_config,
    validate_tencent_sms_config,
    validate_sms_config,
    validate_cloud_service_config
)


class TestSMTPConfigValidation:
    """测试SMTP配置验证"""
    
    def test_validate_smtp_config_missing_fields(self):
        """测试缺少必需字段的SMTP配置"""
        # 缺少smtp_host
        config = {
            "smtp_port": 465,
            "username": "test@example.com",
            "password": "password"
        }
        is_valid, error_msg = validate_smtp_config(config)
        assert not is_valid
        assert "缺少必需字段" in error_msg
        assert "smtp_host" in error_msg
    
    def test_validate_smtp_config_invalid_port(self):
        """测试无效端口号的SMTP配置"""
        # 端口号超出范围
        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 99999,
            "username": "test@example.com",
            "password": "password"
        }
        is_valid, error_msg = validate_smtp_config(config)
        assert not is_valid
        assert "端口必须在1-65535之间" in error_msg
        
        # 端口号不是数字
        config["smtp_port"] = "invalid"
        is_valid, error_msg = validate_smtp_config(config)
        assert not is_valid
        assert "端口必须是有效的数字" in error_msg
    
    @patch('smtplib.SMTP_SSL')
    def test_validate_smtp_config_success_ssl(self, mock_smtp_ssl):
        """测试成功验证SSL SMTP配置"""
        # Mock SMTP服务器
        mock_server = MagicMock()
        mock_smtp_ssl.return_value = mock_server
        
        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "username": "test@example.com",
            "password": "password",
            "use_ssl": True
        }
        
        is_valid, error_msg = validate_smtp_config(config)
        
        assert is_valid
        assert "验证成功" in error_msg
        mock_smtp_ssl.assert_called_once_with("smtp.example.com", 465, timeout=10)
        mock_server.login.assert_called_once_with("test@example.com", "password")
        mock_server.quit.assert_called()
    
    @patch('smtplib.SMTP')
    def test_validate_smtp_config_success_tls(self, mock_smtp):
        """测试成功验证TLS SMTP配置"""
        # Mock SMTP服务器
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "test@example.com",
            "password": "password",
            "use_ssl": False,
            "use_tls": True
        }
        
        is_valid, error_msg = validate_smtp_config(config)
        
        assert is_valid
        assert "验证成功" in error_msg
        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@example.com", "password")
        mock_server.quit.assert_called()
    
    @patch('smtplib.SMTP_SSL')
    def test_validate_smtp_config_auth_failure(self, mock_smtp_ssl):
        """测试SMTP认证失败"""
        # Mock SMTP服务器认证失败
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
        mock_smtp_ssl.return_value = mock_server
        
        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "username": "test@example.com",
            "password": "wrong_password",
            "use_ssl": True
        }
        
        is_valid, error_msg = validate_smtp_config(config)
        
        assert not is_valid
        assert "认证失败" in error_msg
    
    @patch('smtplib.SMTP_SSL')
    def test_validate_smtp_config_connection_error(self, mock_smtp_ssl):
        """测试SMTP连接失败"""
        # Mock连接失败
        mock_smtp_ssl.side_effect = smtplib.SMTPConnectError(421, b"Service not available")
        
        config = {
            "smtp_host": "invalid.example.com",
            "smtp_port": 465,
            "username": "test@example.com",
            "password": "password",
            "use_ssl": True
        }
        
        is_valid, error_msg = validate_smtp_config(config)
        
        assert not is_valid
        assert "无法连接" in error_msg
    
    @patch('smtplib.SMTP_SSL')
    def test_validate_smtp_config_timeout(self, mock_smtp_ssl):
        """测试SMTP连接超时"""
        # Mock超时
        mock_smtp_ssl.side_effect = TimeoutError()
        
        config = {
            "smtp_host": "slow.example.com",
            "smtp_port": 465,
            "username": "test@example.com",
            "password": "password",
            "use_ssl": True
        }
        
        is_valid, error_msg = validate_smtp_config(config)
        
        assert not is_valid
        assert "超时" in error_msg


class TestAliyunSMSConfigValidation:
    """测试阿里云短信配置验证"""
    
    def test_validate_aliyun_sms_config_missing_fields(self):
        """测试缺少必需字段的阿里云短信配置"""
        # 缺少access_key_secret
        config = {
            "access_key_id": "test_key_id",
            "sign_name": "测试签名"
        }
        is_valid, error_msg = validate_aliyun_sms_config(config)
        assert not is_valid
        assert "缺少必需字段" in error_msg
        assert "access_key_secret" in error_msg
    
    def test_validate_aliyun_sms_config_empty_fields(self):
        """测试空字段的阿里云短信配置"""
        config = {
            "access_key_id": "",
            "access_key_secret": "test_secret",
            "sign_name": "测试签名"
        }
        is_valid, error_msg = validate_aliyun_sms_config(config)
        assert not is_valid
        assert "不能为空" in error_msg
    
    @patch('httpx.Client')
    def test_validate_aliyun_sms_config_success(self, mock_client_class):
        """测试成功验证阿里云短信配置"""
        # Mock HTTP响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Code": "OK"}
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        config = {
            "access_key_id": "test_key_id",
            "access_key_secret": "test_secret",
            "sign_name": "测试签名"
        }
        
        is_valid, error_msg = validate_aliyun_sms_config(config)
        
        assert is_valid
        assert "验证成功" in error_msg
    
    @patch('httpx.Client')
    def test_validate_aliyun_sms_config_invalid_key(self, mock_client_class):
        """测试无效的AccessKey"""
        # Mock HTTP响应 - 无效的AccessKey
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Code": "InvalidAccessKeyId.NotFound",
            "Message": "Specified access key is not found."
        }
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        config = {
            "access_key_id": "invalid_key",
            "access_key_secret": "test_secret",
            "sign_name": "测试签名"
        }
        
        is_valid, error_msg = validate_aliyun_sms_config(config)
        
        assert not is_valid
        assert "AccessKey ID无效" in error_msg
    
    @patch('httpx.Client')
    def test_validate_aliyun_sms_config_wrong_secret(self, mock_client_class):
        """测试错误的AccessKey Secret"""
        # Mock HTTP响应 - 签名不匹配
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Code": "SignatureDoesNotMatch",
            "Message": "Specified signature is not matched with our calculation."
        }
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        config = {
            "access_key_id": "test_key_id",
            "access_key_secret": "wrong_secret",
            "sign_name": "测试签名"
        }
        
        is_valid, error_msg = validate_aliyun_sms_config(config)
        
        assert not is_valid
        assert "AccessKey Secret错误" in error_msg
    
    @patch('httpx.Client')
    def test_validate_aliyun_sms_config_sign_not_found(self, mock_client_class):
        """测试签名不存在但凭证有效"""
        # Mock HTTP响应 - 签名不存在
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Code": "InvalidSign.NotFound",
            "Message": "The specified sign does not exist."
        }
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        config = {
            "access_key_id": "test_key_id",
            "access_key_secret": "test_secret",
            "sign_name": "不存在的签名"
        }
        
        is_valid, error_msg = validate_aliyun_sms_config(config)
        
        # 签名不存在，但凭证有效，应该返回成功
        assert is_valid
        assert "凭证有效" in error_msg


class TestTencentSMSConfigValidation:
    """测试腾讯云短信配置验证"""
    
    def test_validate_tencent_sms_config_missing_fields(self):
        """测试缺少必需字段的腾讯云短信配置"""
        # 缺少sdk_app_id
        config = {
            "secret_id": "test_id",
            "secret_key": "test_key",
            "sign_name": "测试签名"
        }
        is_valid, error_msg = validate_tencent_sms_config(config)
        assert not is_valid
        assert "缺少必需字段" in error_msg
        assert "sdk_app_id" in error_msg
    
    def test_validate_tencent_sms_config_empty_fields(self):
        """测试空字段的腾讯云短信配置"""
        config = {
            "secret_id": "",
            "secret_key": "test_key",
            "sdk_app_id": "1400000000",
            "sign_name": "测试签名"
        }
        is_valid, error_msg = validate_tencent_sms_config(config)
        assert not is_valid
        assert "不能为空" in error_msg
    
    @patch('httpx.Client')
    def test_validate_tencent_sms_config_success(self, mock_client_class):
        """测试成功验证腾讯云短信配置"""
        # Mock HTTP响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Response": {
                "DescribeSignListStatus": []
            }
        }
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        config = {
            "secret_id": "test_id",
            "secret_key": "test_key",
            "sdk_app_id": "1400000000",
            "sign_name": "测试签名"
        }
        
        is_valid, error_msg = validate_tencent_sms_config(config)
        
        assert is_valid
        assert "验证成功" in error_msg
    
    @patch('httpx.Client')
    def test_validate_tencent_sms_config_auth_failure(self, mock_client_class):
        """测试腾讯云认证失败"""
        # Mock HTTP响应 - 认证失败
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Response": {
                "Error": {
                    "Code": "AuthFailure.SignatureFailure",
                    "Message": "The provided credentials could not be validated."
                }
            }
        }
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        config = {
            "secret_id": "invalid_id",
            "secret_key": "invalid_key",
            "sdk_app_id": "1400000000",
            "sign_name": "测试签名"
        }
        
        is_valid, error_msg = validate_tencent_sms_config(config)
        
        assert not is_valid
        assert "认证失败" in error_msg
    
    @patch('httpx.Client')
    def test_validate_tencent_sms_config_invalid_parameter(self, mock_client_class):
        """测试腾讯云参数错误但凭证有效"""
        # Mock HTTP响应 - 参数错误
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Response": {
                "Error": {
                    "Code": "InvalidParameter",
                    "Message": "Invalid parameter."
                }
            }
        }
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        config = {
            "secret_id": "test_id",
            "secret_key": "test_key",
            "sdk_app_id": "1400000000",
            "sign_name": "测试签名"
        }
        
        is_valid, error_msg = validate_tencent_sms_config(config)
        
        # 参数错误，但凭证有效，应该返回成功
        assert is_valid
        assert "凭证有效" in error_msg


class TestSMSConfigValidation:
    """测试短信配置验证（多提供商）"""
    
    @patch('httpx.Client')
    def test_validate_sms_config_aliyun(self, mock_client_class):
        """测试验证阿里云短信配置"""
        # Mock HTTP响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Code": "OK"}
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        config = {
            "access_key_id": "test_key_id",
            "access_key_secret": "test_secret",
            "sign_name": "测试签名"
        }
        
        is_valid, error_msg = validate_sms_config("aliyun", config)
        
        assert is_valid
        assert "验证成功" in error_msg
    
    @patch('httpx.Client')
    def test_validate_sms_config_tencent(self, mock_client_class):
        """测试验证腾讯云短信配置"""
        # Mock HTTP响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Response": {
                "DescribeSignListStatus": []
            }
        }
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        config = {
            "secret_id": "test_id",
            "secret_key": "test_key",
            "sdk_app_id": "1400000000",
            "sign_name": "测试签名"
        }
        
        is_valid, error_msg = validate_sms_config("tencent", config)
        
        assert is_valid
        assert "验证成功" in error_msg
    
    def test_validate_sms_config_unsupported_provider(self):
        """测试不支持的短信服务提供商"""
        config = {
            "api_key": "test_key"
        }
        
        is_valid, error_msg = validate_sms_config("unsupported_provider", config)
        
        assert not is_valid
        assert "不支持的短信服务提供商" in error_msg


class TestCloudServiceConfigValidation:
    """测试云服务配置验证（统一接口）"""
    
    @patch('smtplib.SMTP_SSL')
    def test_validate_cloud_service_config_email(self, mock_smtp_ssl):
        """测试验证邮件服务配置"""
        # Mock SMTP服务器
        mock_server = MagicMock()
        mock_smtp_ssl.return_value = mock_server
        
        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "username": "test@example.com",
            "password": "password",
            "use_ssl": True
        }
        
        is_valid, error_msg = validate_cloud_service_config("email", "aliyun", config)
        
        assert is_valid
        assert "验证成功" in error_msg
    
    @patch('httpx.Client')
    def test_validate_cloud_service_config_sms(self, mock_client_class):
        """测试验证短信服务配置"""
        # Mock HTTP响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Code": "OK"}
        
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        config = {
            "access_key_id": "test_key_id",
            "access_key_secret": "test_secret",
            "sign_name": "测试签名"
        }
        
        is_valid, error_msg = validate_cloud_service_config("sms", "aliyun", config)
        
        assert is_valid
        assert "验证成功" in error_msg
    
    def test_validate_cloud_service_config_unsupported_type(self):
        """测试不支持的服务类型"""
        config = {}
        
        is_valid, error_msg = validate_cloud_service_config("unsupported_type", "provider", config)
        
        assert not is_valid
        assert "不支持的服务类型" in error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
