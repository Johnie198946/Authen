"""
通知消息发布器测试

测试消息发布到RabbitMQ队列的功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from shared.notification_publisher import (
    publish_email_notification,
    publish_sms_notification,
    publish_verification_email,
    publish_verification_sms,
    publish_subscription_expiry_reminder,
    QUEUE_EMAIL,
    QUEUE_SMS
)


class TestNotificationPublisher:
    """通知发布器测试"""
    
    @patch('shared.notification_publisher.get_rabbitmq_channel')
    def test_publish_email_notification(self, mock_get_channel):
        """测试发布邮件通知"""
        mock_channel = Mock()
        mock_get_channel.return_value = mock_channel
        
        result = publish_email_notification(
            to='test@example.com',
            subject='Test Subject',
            body='Test Body'
        )
        
        assert result is True
        
        # 验证消息被发布
        mock_channel.basic_publish.assert_called_once()
        call_args = mock_channel.basic_publish.call_args
        
        # 验证routing_key
        assert call_args[1]['routing_key'] == QUEUE_EMAIL
        
        # 验证消息内容
        message = json.loads(call_args[1]['body'])
        assert message['type'] == 'email'
        assert message['to'] == 'test@example.com'
        assert message['subject'] == 'Test Subject'
        assert message['body'] == 'Test Body'
        assert message['retry_count'] == 0
        
        # 验证通道被关闭
        mock_channel.close.assert_called_once()
    
    @patch('shared.notification_publisher.get_rabbitmq_channel')
    def test_publish_email_with_template(self, mock_get_channel):
        """测试发布带模板的邮件通知"""
        mock_channel = Mock()
        mock_get_channel.return_value = mock_channel
        
        result = publish_email_notification(
            to='test@example.com',
            subject='Test',
            body='Test',
            template='welcome_email'
        )
        
        assert result is True
        
        # 验证消息包含模板
        call_args = mock_channel.basic_publish.call_args
        message = json.loads(call_args[1]['body'])
        assert message['template'] == 'welcome_email'
    
    @patch('shared.notification_publisher.get_rabbitmq_channel')
    def test_publish_email_with_custom_fields(self, mock_get_channel):
        """测试发布带自定义字段的邮件通知"""
        mock_channel = Mock()
        mock_get_channel.return_value = mock_channel
        
        result = publish_email_notification(
            to='test@example.com',
            subject='Test',
            body='Test',
            custom_field='custom_value',
            another_field=123
        )
        
        assert result is True
        
        # 验证消息包含自定义字段
        call_args = mock_channel.basic_publish.call_args
        message = json.loads(call_args[1]['body'])
        assert message['custom_field'] == 'custom_value'
        assert message['another_field'] == 123
    
    @patch('shared.notification_publisher.get_rabbitmq_channel')
    def test_publish_sms_notification(self, mock_get_channel):
        """测试发布短信通知"""
        mock_channel = Mock()
        mock_get_channel.return_value = mock_channel
        
        result = publish_sms_notification(
            to='+8613800138000',
            content='Test SMS'
        )
        
        assert result is True
        
        # 验证消息被发布
        mock_channel.basic_publish.assert_called_once()
        call_args = mock_channel.basic_publish.call_args
        
        # 验证routing_key
        assert call_args[1]['routing_key'] == QUEUE_SMS
        
        # 验证消息内容
        message = json.loads(call_args[1]['body'])
        assert message['type'] == 'sms'
        assert message['to'] == '+8613800138000'
        assert message['content'] == 'Test SMS'
        assert message['retry_count'] == 0
    
    @patch('shared.notification_publisher.get_rabbitmq_channel')
    def test_publish_verification_email(self, mock_get_channel):
        """测试发布验证邮件"""
        mock_channel = Mock()
        mock_get_channel.return_value = mock_channel
        
        result = publish_verification_email(
            to='user@example.com',
            verification_code='123456',
            username='testuser'
        )
        
        assert result is True
        
        # 验证消息内容
        call_args = mock_channel.basic_publish.call_args
        message = json.loads(call_args[1]['body'])
        
        assert message['type'] == 'email'
        assert message['to'] == 'user@example.com'
        assert message['template'] == 'email_verification'
        assert message['verification_code'] == '123456'
        assert message['username'] == 'testuser'
        assert '123456' in message['body']
    
    @patch('shared.notification_publisher.get_rabbitmq_channel')
    def test_publish_verification_sms(self, mock_get_channel):
        """测试发布验证短信"""
        mock_channel = Mock()
        mock_get_channel.return_value = mock_channel
        
        result = publish_verification_sms(
            to='+8613800138000',
            verification_code='654321'
        )
        
        assert result is True
        
        # 验证消息内容
        call_args = mock_channel.basic_publish.call_args
        message = json.loads(call_args[1]['body'])
        
        assert message['type'] == 'sms'
        assert message['to'] == '+8613800138000'
        assert message['template'] == 'sms_verification'
        assert message['verification_code'] == '654321'
        assert '654321' in message['content']
    
    @patch('shared.notification_publisher.get_rabbitmq_channel')
    def test_publish_subscription_expiry_reminder(self, mock_get_channel):
        """测试发布订阅到期提醒"""
        mock_channel = Mock()
        mock_get_channel.return_value = mock_channel
        
        result = publish_subscription_expiry_reminder(
            to='user@example.com',
            username='testuser',
            days_remaining=7,
            plan_name='Premium Plan'
        )
        
        assert result is True
        
        # 验证消息内容
        call_args = mock_channel.basic_publish.call_args
        message = json.loads(call_args[1]['body'])
        
        assert message['type'] == 'email'
        assert message['to'] == 'user@example.com'
        assert message['template'] == 'subscription_expiry_reminder'
        assert message['username'] == 'testuser'
        assert message['days_remaining'] == 7
        assert message['plan_name'] == 'Premium Plan'
        assert '7' in message['subject']
        assert 'Premium Plan' in message['body']
    
    @patch('shared.notification_publisher.get_rabbitmq_channel')
    def test_publish_email_failure(self, mock_get_channel):
        """测试邮件发布失败"""
        mock_channel = Mock()
        mock_channel.basic_publish.side_effect = Exception("Connection error")
        mock_get_channel.return_value = mock_channel
        
        result = publish_email_notification(
            to='test@example.com',
            subject='Test',
            body='Test'
        )
        
        assert result is False
    
    @patch('shared.notification_publisher.get_rabbitmq_channel')
    def test_publish_sms_failure(self, mock_get_channel):
        """测试短信发布失败"""
        mock_channel = Mock()
        mock_channel.basic_publish.side_effect = Exception("Connection error")
        mock_get_channel.return_value = mock_channel
        
        result = publish_sms_notification(
            to='+8613800138000',
            content='Test'
        )
        
        assert result is False


class TestMessagePersistence:
    """消息持久化测试"""
    
    @patch('shared.notification_publisher.get_rabbitmq_channel')
    def test_email_message_persistence(self, mock_get_channel):
        """测试邮件消息持久化"""
        mock_channel = Mock()
        mock_get_channel.return_value = mock_channel
        
        publish_email_notification(
            to='test@example.com',
            subject='Test',
            body='Test'
        )
        
        # 验证消息属性包含持久化标记
        call_args = mock_channel.basic_publish.call_args
        properties = call_args[1]['properties']
        
        assert properties.delivery_mode == 2  # 持久化
        assert properties.content_type == 'application/json'
    
    @patch('shared.notification_publisher.get_rabbitmq_channel')
    def test_sms_message_persistence(self, mock_get_channel):
        """测试短信消息持久化"""
        mock_channel = Mock()
        mock_get_channel.return_value = mock_channel
        
        publish_sms_notification(
            to='+8613800138000',
            content='Test'
        )
        
        # 验证消息属性包含持久化标记
        call_args = mock_channel.basic_publish.call_args
        properties = call_args[1]['properties']
        
        assert properties.delivery_mode == 2  # 持久化
        assert properties.content_type == 'application/json'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
