"""
短信服务单元测试

测试短信发送、模板渲染和重试机制。
"""
import sys
import os
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import Mock, patch, MagicMock
from services.notification.sms_service import (
    SMSService,
    AliyunSMSClient,
    TencentSMSClient
)
from shared.models.system import CloudServiceConfig, MessageTemplate


class TestAliyunSMSClient:
    """测试阿里云短信客户端"""

    @staticmethod
    def make_client(response_code='OK'):
        sdk_client = Mock()
        sdk_client.send_sms.return_value = SimpleNamespace(
            body=SimpleNamespace(code=response_code, request_id='request-1')
        )
        request_factory = Mock(
            side_effect=lambda **kwargs: SimpleNamespace(**kwargs)
        )
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名',
            'region_id': 'cn-qingdao',
        }
        client = AliyunSMSClient(
            config,
            sdk_client=sdk_client,
            request_factory=request_factory,
        )
        return client, sdk_client, request_factory
    
    def test_init_with_valid_config(self):
        """测试使用有效配置初始化"""
        config = {
            'access_key_id': 'test_key_id',
            'access_key_secret': 'test_key_secret',
            'sign_name': '测试签名'
        }
        
        client = AliyunSMSClient(
            config, sdk_client=Mock(), request_factory=Mock()
        )
        
        assert client.access_key_id == 'test_key_id'
        assert client.access_key_secret == 'test_key_secret'
        assert client.sign_name == '测试签名'
        assert client.endpoint == 'dysmsapi.aliyuncs.com'
        assert client.region_id == 'cn-qingdao'
    
    def test_init_with_invalid_config(self):
        """测试使用无效配置初始化"""
        config = {
            'access_key_id': 'test_key_id'
            # 缺少必需字段
        }
        
        with pytest.raises(ValueError, match="阿里云短信配置不完整"):
            AliyunSMSClient(config)
    
    def test_send_sms_success(self):
        """测试成功发送短信"""
        client, sdk_client, request_factory = self.make_client()
        result = client.send_sms(
            phone_number='+8613800138000',
            template_code='SMS_123456789',
            template_param={'code': '123456'}
        )
        
        assert result is True
        request = request_factory.call_args.kwargs
        assert request['phone_numbers'] == '13800138000'
        assert request['sign_name'] == '测试签名'
        assert request['template_code'] == 'SMS_123456789'
        assert request['template_param'] == '{"code": "123456"}'
        sdk_client.send_sms.assert_called_once()
    
    def test_send_sms_failure(self):
        """测试发送短信失败"""
        client, _, _ = self.make_client('isv.BUSINESS_LIMIT_CONTROL')
        result = client.send_sms(
            phone_number='+8613800138000',
            template_code='SMS_123456789',
            template_param={'code': '123456'}
        )
        
        assert result is False

    def test_masks_phone_for_logs(self):
        assert AliyunSMSClient._masked_phone('+8613800138000') == '*******8000'


class TestTencentSMSClient:
    """测试腾讯云短信客户端"""
    
    def test_init_with_valid_config(self):
        """测试使用有效配置初始化"""
        config = {
            'secret_id': 'test_secret_id',
            'secret_key': 'test_secret_key',
            'sdk_app_id': '1400000000',
            'sign_name': '测试签名'
        }
        
        client = TencentSMSClient(config)
        
        assert client.secret_id == 'test_secret_id'
        assert client.secret_key == 'test_secret_key'
        assert client.sdk_app_id == '1400000000'
        assert client.sign_name == '测试签名'
        assert client.endpoint == 'sms.tencentcloudapi.com'
    
    def test_init_with_invalid_config(self):
        """测试使用无效配置初始化"""
        config = {
            'secret_id': 'test_secret_id'
            # 缺少必需字段
        }
        
        with pytest.raises(ValueError, match="腾讯云短信配置不完整"):
            TencentSMSClient(config)
    
    @patch('services.notification.sms_service.httpx.Client')
    def test_send_sms_success(self, mock_client):
        """测试成功发送短信"""
        config = {
            'secret_id': 'test_secret_id',
            'secret_key': 'test_secret_key',
            'sdk_app_id': '1400000000',
            'sign_name': '测试签名'
        }
        
        # Mock HTTP响应
        mock_response = Mock()
        mock_response.json.return_value = {
            'Response': {
                'SendStatusSet': [{'Code': 'Ok'}]
            }
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        client = TencentSMSClient(config)
        result = client.send_sms(
            phone_number='+8613800138000',
            template_id='123456',
            template_param=['123456']
        )
        
        assert result is True
    
    @patch('services.notification.sms_service.httpx.Client')
    def test_send_sms_failure(self, mock_client):
        """测试发送短信失败"""
        config = {
            'secret_id': 'test_secret_id',
            'secret_key': 'test_secret_key',
            'sdk_app_id': '1400000000',
            'sign_name': '测试签名'
        }
        
        # Mock HTTP响应（失败）
        mock_response = Mock()
        mock_response.json.return_value = {
            'Response': {
                'Error': {
                    'Code': 'FailedOperation.ContainSensitiveWord',
                    'Message': '短信内容包含敏感词'
                }
            }
        }
        mock_client.return_value.__enter__.return_value.post.return_value = mock_response
        
        client = TencentSMSClient(config)
        result = client.send_sms(
            phone_number='+8613800138000',
            template_id='123456',
            template_param=['123456']
        )
        
        assert result is False
    
    def test_phone_number_formatting(self):
        """测试手机号格式化"""
        config = {
            'secret_id': 'test_secret_id',
            'secret_key': 'test_secret_key',
            'sdk_app_id': '1400000000',
            'sign_name': '测试签名'
        }
        
        client = TencentSMSClient(config)
        
        # 测试不带国家码的手机号会自动添加+86
        with patch('services.notification.sms_service.httpx.Client') as mock_client:
            mock_response = Mock()
            mock_response.json.return_value = {'Response': {}}
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            client.send_sms(
                phone_number='13800138000',  # 不带+86
                template_id='123456',
                template_param=['123456']
            )
            
            # 验证请求体中的手机号包含+86
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            import json
            payload = json.loads(call_args[1]['content'])
            assert payload['PhoneNumberSet'][0] == '+8613800138000'


class TestSMSService:
    """测试短信服务"""
    
    @patch('services.notification.sms_service.get_db')
    def test_load_aliyun_config(self, mock_get_db):
        """测试加载阿里云配置"""
        # Mock数据库查询
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        
        mock_config = CloudServiceConfig(
            service_type='sms',
            provider='aliyun',
            config={
                'access_key_id': 'test_key_id',
                'access_key_secret': 'test_key_secret',
                'sign_name': '测试签名'
            },
            is_active=True
        )
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config
        
        with patch.object(AliyunSMSClient, '_create_sdk_client', return_value=Mock()), \
             patch.object(AliyunSMSClient, '_load_request_factory', return_value=Mock()):
            service = SMSService()
        
        assert service.sms_config is not None
        assert isinstance(service.sms_client, AliyunSMSClient)

    @patch.dict(os.environ, {
        'SMS_PROVIDER': 'aliyun',
        'ALIBABA_CLOUD_ACCESS_KEY_ID': 'env_key_id',
        'ALIBABA_CLOUD_ACCESS_KEY_SECRET': 'env_key_secret',
        'ALIYUN_SMS_SIGN_NAME': '深圳市时空感应网络科技',
        'ALIYUN_SMS_TEMPLATE_CODE': 'SMS_511560412',
        'ALIYUN_SMS_REGION_ID': 'cn-qingdao',
    }, clear=True)
    @patch('services.notification.sms_service.get_db')
    def test_load_aliyun_config_from_environment(self, mock_get_db):
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch.object(AliyunSMSClient, '_create_sdk_client', return_value=Mock()), \
             patch.object(AliyunSMSClient, '_load_request_factory', return_value=Mock()):
            service = SMSService()

        assert isinstance(service.sms_client, AliyunSMSClient)
        assert service.sms_config['template_code'] == 'SMS_511560412'
        assert service.sms_client.region_id == 'cn-qingdao'
    
    @patch('services.notification.sms_service.get_db')
    def test_load_tencent_config(self, mock_get_db):
        """测试加载腾讯云配置"""
        # Mock数据库查询
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        
        mock_config = CloudServiceConfig(
            service_type='sms',
            provider='tencent',
            config={
                'secret_id': 'test_secret_id',
                'secret_key': 'test_secret_key',
                'sdk_app_id': '1400000000',
                'sign_name': '测试签名'
            },
            is_active=True
        )
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config
        
        service = SMSService()
        
        assert service.sms_config is not None
        assert isinstance(service.sms_client, TencentSMSClient)
    
    @patch('services.notification.sms_service.get_db')
    def test_load_config_not_found(self, mock_get_db):
        """测试配置不存在"""
        # Mock数据库查询（返回None）
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        service = SMSService()
        
        assert service.sms_config is None
        assert service.sms_client is None
    
    def test_render_template(self):
        """测试模板渲染"""
        service = SMSService()
        
        template_content = "您的验证码是: {{ code }}，{{ minutes }}分钟内有效。"
        variables = {'code': '123456', 'minutes': 15}
        
        result = service.render_template(template_content, variables)
        
        assert result == "您的验证码是: 123456，15分钟内有效。"
    
    def test_render_template_error(self):
        """测试模板渲染错误"""
        service = SMSService()
        
        template_content = "您的验证码是: {{ code }，{{ minutes }}分钟内有效。"  # 语法错误
        variables = {'code': '123456', 'minutes': 15}
        
        from jinja2 import TemplateError
        with pytest.raises(TemplateError):
            service.render_template(template_content, variables)
    
    @patch('services.notification.sms_service.get_db')
    def test_send_sms_without_config(self, mock_get_db):
        """测试未配置时发送短信"""
        # Mock数据库查询（返回None）
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        service = SMSService()
        result = service.send_sms(
            to_phone='+8613800138000',
            content='测试短信'
        )
        
        assert result is False
    
    @patch('services.notification.sms_service.get_db')
    def test_send_sms_with_aliyun(self, mock_get_db):
        """测试使用阿里云发送短信"""
        # Mock数据库查询
        mock_db = Mock()
        
        mock_config = CloudServiceConfig(
            service_type='sms',
            provider='aliyun',
            config={
                'access_key_id': 'test_key_id',
                'access_key_secret': 'test_key_secret',
                'sign_name': '测试签名'
            },
            is_active=True
        )
        
        mock_template = MessageTemplate(
            name='sms_verification',
            type='sms',
            content='您的验证码是: {{ code }}',
            variables={
                'template_code': 'SMS_123456789'
            }
        )
        
        # 设置多次调用的返回值
        def get_db_side_effect():
            yield mock_db
        
        mock_get_db.side_effect = get_db_side_effect
        
        # 第一次调用返回config，后续调用返回template
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_config,
            mock_template
        ]
        
        with patch.object(AliyunSMSClient, '_create_sdk_client', return_value=Mock()), \
             patch.object(AliyunSMSClient, '_load_request_factory', return_value=Mock()), \
             patch.object(AliyunSMSClient, 'send_sms', return_value=True) as mock_send:
            service = SMSService()
            result = service.send_sms(
                to_phone='+8613800138000',
                content='',
                template_name='sms_verification',
                template_variables={'code': '123456'}
            )
            
            assert result is True
            mock_send.assert_called_once()
    
    @patch('services.notification.sms_service.get_db')
    def test_send_sms_with_tencent(self, mock_get_db):
        """测试使用腾讯云发送短信"""
        # Mock数据库查询
        mock_db = Mock()
        
        mock_config = CloudServiceConfig(
            service_type='sms',
            provider='tencent',
            config={
                'secret_id': 'test_secret_id',
                'secret_key': 'test_secret_key',
                'sdk_app_id': '1400000000',
                'sign_name': '测试签名'
            },
            is_active=True
        )
        
        mock_template = MessageTemplate(
            name='sms_verification',
            type='sms',
            content='您的验证码是: {{ code }}',
            variables={
                'template_id': '123456'
            }
        )
        
        # 设置多次调用的返回值
        def get_db_side_effect():
            yield mock_db
        
        mock_get_db.side_effect = get_db_side_effect
        
        # 第一次调用返回config，后续调用返回template
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_config,
            mock_template
        ]
        
        with patch.object(TencentSMSClient, 'send_sms', return_value=True) as mock_send:
            service = SMSService()
            result = service.send_sms(
                to_phone='+8613800138000',
                content='',
                template_name='sms_verification',
                template_variables={'code': '123456'}
            )
            
            assert result is True
            mock_send.assert_called_once()
    
    @patch('services.notification.sms_service.get_db')
    def test_send_verification_sms(self, mock_get_db):
        """测试发送验证短信"""
        # Mock数据库查询
        mock_db = Mock()
        
        mock_config = CloudServiceConfig(
            service_type='sms',
            provider='aliyun',
            config={
                'access_key_id': 'test_key_id',
                'access_key_secret': 'test_key_secret',
                'sign_name': '测试签名'
            },
            is_active=True
        )
        
        mock_template = MessageTemplate(
            name='sms_verification',
            type='sms',
            content='您的验证码是: {{ code }}',
            variables={
                'template_code': 'SMS_123456789'
            }
        )
        
        # 设置多次调用的返回值
        def get_db_side_effect():
            yield mock_db
        
        mock_get_db.side_effect = get_db_side_effect
        
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_config,
            mock_template
        ]
        
        with patch.object(AliyunSMSClient, '_create_sdk_client', return_value=Mock()), \
             patch.object(AliyunSMSClient, '_load_request_factory', return_value=Mock()), \
             patch.object(AliyunSMSClient, 'send_sms', return_value=True) as mock_send:
            service = SMSService()
            result = service.send_verification_sms(
                to_phone='+8613800138000',
                verification_code='123456'
            )
            
            assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
