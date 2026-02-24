"""
通知服务集成测试

测试邮件发送的完整工作流程，包括：
- 消息队列消费
- 模板渲染
- SMTP发送
- 重试机制
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import json
import uuid
from unittest.mock import Mock, patch, MagicMock
from services.notification.main import NotificationConsumer
from services.notification.email_service import EmailService
from shared.models.system import CloudServiceConfig, MessageTemplate


@pytest.fixture
def notification_consumer():
    """创建通知消费者实例"""
    with patch('services.notification.main.get_rabbitmq_connection'):
        consumer = NotificationConsumer()
        consumer.channel = Mock()
        return consumer


@pytest.fixture
def mock_email_service():
    """创建模拟邮件服务"""
    with patch('services.notification.main.email_service') as mock:
        mock.send_email.return_value = True
        yield mock


class TestNotificationIntegration:
    """通知服务集成测试"""
    
    def test_email_message_routing(self, notification_consumer, mock_email_service):
        """测试邮件消息路由"""
        message = {
            'type': 'email',
            'to': 'user@example.com',
            'subject': 'Test Email',
            'body': 'Test Body',
            'html': True
        }
        
        result = notification_consumer.route_message(message)
        
        assert result is True
        mock_email_service.send_email.assert_called_once_with(
            to_email='user@example.com',
            subject='Test Email',
            body='Test Body',
            template_name=None,
            template_variables={},
            html=True
        )
    
    def test_email_message_with_template(self, notification_consumer, mock_email_service):
        """测试使用模板的邮件消息"""
        message = {
            'type': 'email',
            'to': 'user@example.com',
            'template': 'email_verification',
            'template_variables': {
                'email': 'user@example.com',
                'verification_link': 'https://example.com/verify?token=abc'
            }
        }
        
        result = notification_consumer.route_message(message)
        
        assert result is True
        mock_email_service.send_email.assert_called_once()
        call_args = mock_email_service.send_email.call_args
        assert call_args[1]['template_name'] == 'email_verification'
        assert call_args[1]['template_variables']['verification_link'] == 'https://example.com/verify?token=abc'
    
    def test_email_send_failure_triggers_retry(self, notification_consumer, mock_email_service):
        """测试邮件发送失败触发重试"""
        # 模拟发送失败
        mock_email_service.send_email.return_value = False
        
        message = {
            'type': 'email',
            'to': 'user@example.com',
            'subject': 'Test',
            'body': 'Test'
        }
        
        # 模拟消息处理
        body = json.dumps(message).encode()
        method = Mock()
        method.delivery_tag = 1
        
        notification_consumer.process_message(
            notification_consumer.channel,
            method,
            None,
            body
        )
        
        # 验证消息被发送到重试队列
        notification_consumer.channel.basic_publish.assert_called_once()
        call_args = notification_consumer.channel.basic_publish.call_args
        assert call_args[1]['routing_key'] == 'notifications.retry'
        
        # 验证重试计数增加
        retry_message = json.loads(call_args[1]['body'])
        assert retry_message['retry_count'] == 1
    
    def test_max_retry_attempts_reached(self, notification_consumer, mock_email_service):
        """测试达到最大重试次数"""
        # 模拟发送失败
        mock_email_service.send_email.return_value = False
        
        message = {
            'type': 'email',
            'to': 'user@example.com',
            'subject': 'Test',
            'body': 'Test',
            'retry_count': 3  # 已达到最大重试次数
        }
        
        body = json.dumps(message).encode()
        method = Mock()
        method.delivery_tag = 1
        
        notification_consumer.process_message(
            notification_consumer.channel,
            method,
            None,
            body
        )
        
        # 验证消息被确认（从队列移除）
        notification_consumer.channel.basic_ack.assert_called_once_with(delivery_tag=1)
        
        # 验证没有发送到重试队列
        notification_consumer.channel.basic_publish.assert_not_called()
    
    def test_invalid_message_format(self, notification_consumer):
        """测试无效的消息格式"""
        # 无效的JSON
        body = b'invalid json'
        method = Mock()
        method.delivery_tag = 1
        
        notification_consumer.process_message(
            notification_consumer.channel,
            method,
            None,
            body
        )
        
        # 验证消息被确认（丢弃）
        notification_consumer.channel.basic_ack.assert_called_once_with(delivery_tag=1)
    
    def test_missing_required_fields(self, notification_consumer, mock_email_service):
        """测试缺少必要字段的消息"""
        message = {
            'type': 'email',
            # 缺少 'to' 字段
            'subject': 'Test',
            'body': 'Test'
        }
        
        result = notification_consumer.route_message(message)
        
        assert result is False
    
    @patch('services.notification.email_service.smtplib.SMTP')
    @patch('services.notification.email_service.get_db')
    def test_complete_email_workflow(self, mock_get_db, mock_smtp):
        """测试完整的邮件发送工作流程"""
        # 配置数据库mock
        mock_db = Mock()
        mock_db_iter = Mock()
        mock_db_iter.__iter__ = Mock(return_value=iter([mock_db]))
        mock_db_iter.__next__ = Mock(side_effect=[mock_db, StopIteration])
        
        # 配置SMTP配置
        smtp_config = CloudServiceConfig(
            id=uuid.uuid4(),
            service_type='email',
            provider='gmail',
            config={
                'smtp_host': 'smtp.gmail.com',
                'smtp_port': 587,
                'use_ssl': False,
                'use_tls': True,
                'username': 'test@gmail.com',
                'password': 'testpass',
                'from_email': 'noreply@example.com'
            },
            is_active=True
        )
        
        # 配置邮件模板
        email_template = MessageTemplate(
            id=uuid.uuid4(),
            name='welcome_email',
            type='email',
            subject='Welcome {{ username }}!',
            content='<h1>Hello {{ username }}</h1><p>Welcome to our platform!</p>',
            variables={'username': 'string'}
        )
        
        # 设置查询返回值
        def query_side_effect(model):
            mock_query = Mock()
            if model == CloudServiceConfig:
                mock_query.filter.return_value.first.return_value = smtp_config
            elif model == MessageTemplate:
                mock_query.filter.return_value.first.return_value = email_template
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        mock_db.close = Mock()
        
        # 每次调用get_db都返回新的迭代器
        mock_get_db.return_value = iter([mock_db])
        
        # 配置SMTP mock
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # 创建邮件服务并发送邮件
        email_service = EmailService()
        
        # 重新设置get_db以便send_email调用
        mock_db2 = Mock()
        mock_db2.query.side_effect = query_side_effect
        mock_db2.close = Mock()
        mock_get_db.return_value = iter([mock_db2])
        
        result = email_service.send_email(
            to_email='user@example.com',
            subject='',
            body='',
            template_name='welcome_email',
            template_variables={'username': 'Alice'}
        )
        
        # 验证结果
        assert result is True
        mock_smtp.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()
        
        # 验证邮件内容包含渲染后的变量
        sent_message = mock_server.send_message.call_args[0][0]
        assert 'Alice' in str(sent_message)
    
    def test_retry_message_processing(self, notification_consumer, mock_email_service):
        """测试重试消息处理"""
        # 第一次失败，第二次成功
        mock_email_service.send_email.side_effect = [False, True]
        
        message = {
            'type': 'email',
            'to': 'user@example.com',
            'subject': 'Test',
            'body': 'Test',
            'retry_count': 1
        }
        
        body = json.dumps(message).encode()
        method = Mock()
        method.delivery_tag = 1
        
        # 第一次处理（失败）
        with patch('services.notification.main.time.sleep'):  # 跳过延迟
            notification_consumer.process_retry_message(
                notification_consumer.channel,
                method,
                None,
                body
            )
        
        # 验证发送到重试队列
        assert notification_consumer.channel.basic_publish.called
        
        # 重置mock
        notification_consumer.channel.reset_mock()
        
        # 第二次处理（成功）
        with patch('services.notification.main.time.sleep'):
            notification_consumer.process_retry_message(
                notification_consumer.channel,
                method,
                None,
                body
            )
        
        # 验证消息被确认
        notification_consumer.channel.basic_ack.assert_called_once()
    
    def test_sms_message_routing(self, notification_consumer):
        """测试短信消息路由"""
        message = {
            'type': 'sms',
            'to': '+8613800138000',
            'content': 'Your verification code is 123456'
        }
        
        # Mock SMS service
        with patch('services.notification.main.sms_service.send_sms', return_value=True):
            result = notification_consumer.route_message(message)
            
            # 短信功能应该返回True
            assert result is True
    
    def test_unknown_message_type(self, notification_consumer):
        """测试未知的消息类型"""
        message = {
            'type': 'unknown',
            'data': 'test'
        }
        
        result = notification_consumer.route_message(message)
        
        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
