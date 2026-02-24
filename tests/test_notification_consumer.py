"""
通知服务消费者测试

测试RabbitMQ消费者的消息路由和重试机制
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from services.notification.main import NotificationConsumer, QUEUE_EMAIL, QUEUE_SMS, QUEUE_RETRY


class TestNotificationConsumer:
    """通知消费者测试"""
    
    @pytest.fixture
    def consumer(self):
        """创建消费者实例（mock连接）"""
        with patch('services.notification.main.get_rabbitmq_connection'):
            consumer = NotificationConsumer()
            consumer.channel = Mock()
            return consumer
    
    def test_route_message_email(self, consumer):
        """测试邮件消息路由"""
        message = {
            'type': 'email',
            'to': 'test@example.com',
            'subject': 'Test Email',
            'body': 'This is a test email'
        }
        
        with patch.object(consumer, 'send_email', return_value=True) as mock_send:
            result = consumer.route_message(message)
            
            assert result is True
            mock_send.assert_called_once_with(message)
    
    def test_route_message_sms(self, consumer):
        """测试短信消息路由"""
        message = {
            'type': 'sms',
            'to': '+8613800138000',
            'content': 'Test SMS'
        }
        
        with patch.object(consumer, 'send_sms', return_value=True) as mock_send:
            result = consumer.route_message(message)
            
            assert result is True
            mock_send.assert_called_once_with(message)
    
    def test_route_message_unknown_type(self, consumer):
        """测试未知消息类型"""
        message = {
            'type': 'unknown',
            'data': 'test'
        }
        
        result = consumer.route_message(message)
        assert result is False
    
    def test_send_email_success(self, consumer):
        """测试邮件发送成功"""
        message = {
            'to': 'test@example.com',
            'subject': 'Test Subject',
            'body': 'Test Body'
        }
        
        # Mock email service to avoid database connection
        with patch('services.notification.main.email_service.send_email', return_value=True):
            result = consumer.send_email(message)
            assert result is True
    
    def test_send_email_missing_fields(self, consumer):
        """测试邮件消息缺少必要字段"""
        # 缺少subject
        message = {
            'to': 'test@example.com',
            'body': 'Test Body'
        }
        
        result = consumer.send_email(message)
        assert result is False
    
    def test_send_sms_success(self, consumer):
        """测试短信发送成功"""
        message = {
            'to': '+8613800138000',
            'content': 'Test SMS'
        }
        
        # Mock SMS service to avoid database connection
        with patch('services.notification.main.sms_service.send_sms', return_value=True):
            result = consumer.send_sms(message)
            assert result is True
    
    def test_send_sms_missing_fields(self, consumer):
        """测试短信消息缺少必要字段"""
        # 缺少content
        message = {
            'to': '+8613800138000'
        }
        
        result = consumer.send_sms(message)
        assert result is False
    
    def test_handle_retry_within_limit(self, consumer):
        """测试重试次数未达上限"""
        message = {
            'type': 'email',
            'to': 'test@example.com',
            'subject': 'Test',
            'body': 'Test',
            'retry_count': 1
        }
        delivery_tag = 123
        
        consumer.handle_retry(message, delivery_tag)
        
        # 验证消息被发送到重试队列
        consumer.channel.basic_publish.assert_called_once()
        call_args = consumer.channel.basic_publish.call_args
        
        # 验证routing_key是重试队列
        assert call_args[1]['routing_key'] == QUEUE_RETRY
        
        # 验证retry_count增加
        published_message = json.loads(call_args[1]['body'])
        assert published_message['retry_count'] == 2
        
        # 验证原消息被确认
        consumer.channel.basic_ack.assert_called_once_with(delivery_tag=delivery_tag)
    
    def test_handle_retry_max_attempts(self, consumer):
        """测试重试次数达到上限"""
        message = {
            'type': 'email',
            'to': 'test@example.com',
            'subject': 'Test',
            'body': 'Test',
            'retry_count': 3  # 已达到MAX_RETRY_ATTEMPTS
        }
        delivery_tag = 123
        
        consumer.handle_retry(message, delivery_tag)
        
        # 验证消息未被发送到重试队列
        consumer.channel.basic_publish.assert_not_called()
        
        # 验证消息被确认（丢弃）
        consumer.channel.basic_ack.assert_called_once_with(delivery_tag=delivery_tag)
    
    def test_process_message_success(self, consumer):
        """测试消息处理成功"""
        message = {
            'type': 'email',
            'to': 'test@example.com',
            'subject': 'Test',
            'body': 'Test'
        }
        body = json.dumps(message).encode()
        
        method = Mock()
        method.delivery_tag = 123
        
        with patch.object(consumer, 'route_message', return_value=True):
            consumer.process_message(consumer.channel, method, None, body)
            
            # 验证消息被确认
            consumer.channel.basic_ack.assert_called_once_with(delivery_tag=123)
    
    def test_process_message_failure(self, consumer):
        """测试消息处理失败"""
        message = {
            'type': 'email',
            'to': 'test@example.com',
            'subject': 'Test',
            'body': 'Test'
        }
        body = json.dumps(message).encode()
        
        method = Mock()
        method.delivery_tag = 123
        
        with patch.object(consumer, 'route_message', return_value=False):
            with patch.object(consumer, 'handle_retry'):
                consumer.process_message(consumer.channel, method, None, body)
                
                # 验证进入重试流程
                consumer.handle_retry.assert_called_once()
    
    def test_process_message_invalid_json(self, consumer):
        """测试无效的JSON消息"""
        body = b'invalid json'
        
        method = Mock()
        method.delivery_tag = 123
        
        consumer.process_message(consumer.channel, method, None, body)
        
        # 验证消息被确认（丢弃）
        consumer.channel.basic_ack.assert_called_once_with(delivery_tag=123)
    
    def test_process_message_exception(self, consumer):
        """测试消息处理异常"""
        message = {
            'type': 'email',
            'to': 'test@example.com',
            'subject': 'Test',
            'body': 'Test'
        }
        body = json.dumps(message).encode()
        
        method = Mock()
        method.delivery_tag = 123
        
        with patch.object(consumer, 'route_message', side_effect=Exception("Test error")):
            consumer.process_message(consumer.channel, method, None, body)
            
            # 验证消息被拒绝并重新入队
            consumer.channel.basic_nack.assert_called_once_with(
                delivery_tag=123,
                requeue=True
            )


class TestMessageRouting:
    """消息路由测试"""
    
    def test_email_message_routing(self):
        """测试邮件消息正确路由到邮件处理器"""
        with patch('services.notification.main.get_rabbitmq_connection'):
            consumer = NotificationConsumer()
            consumer.channel = Mock()
            
            message = {
                'type': 'email',
                'to': 'user@example.com',
                'subject': 'Welcome',
                'body': 'Welcome to our platform'
            }
            
            with patch.object(consumer, 'send_email', return_value=True) as mock_email:
                with patch.object(consumer, 'send_sms') as mock_sms:
                    consumer.route_message(message)
                    
                    # 验证只调用了邮件发送
                    mock_email.assert_called_once()
                    mock_sms.assert_not_called()
    
    def test_sms_message_routing(self):
        """测试短信消息正确路由到短信处理器"""
        with patch('services.notification.main.get_rabbitmq_connection'):
            consumer = NotificationConsumer()
            consumer.channel = Mock()
            
            message = {
                'type': 'sms',
                'to': '+8613800138000',
                'content': 'Your verification code is 123456'
            }
            
            with patch.object(consumer, 'send_email') as mock_email:
                with patch.object(consumer, 'send_sms', return_value=True) as mock_sms:
                    consumer.route_message(message)
                    
                    # 验证只调用了短信发送
                    mock_sms.assert_called_once()
                    mock_email.assert_not_called()


class TestRetryMechanism:
    """重试机制测试"""
    
    def test_retry_count_increments(self):
        """测试重试计数递增"""
        with patch('services.notification.main.get_rabbitmq_connection'):
            consumer = NotificationConsumer()
            consumer.channel = Mock()
            
            message = {
                'type': 'email',
                'to': 'test@example.com',
                'subject': 'Test',
                'body': 'Test',
                'retry_count': 0
            }
            
            consumer.handle_retry(message, 123)
            
            # 获取发布的消息
            call_args = consumer.channel.basic_publish.call_args
            published_message = json.loads(call_args[1]['body'])
            
            # 验证retry_count增加到1
            assert published_message['retry_count'] == 1
    
    def test_retry_stops_at_max_attempts(self):
        """测试重试在达到最大次数后停止"""
        with patch('services.notification.main.get_rabbitmq_connection'):
            consumer = NotificationConsumer()
            consumer.channel = Mock()
            
            # 已经重试3次
            message = {
                'type': 'email',
                'to': 'test@example.com',
                'subject': 'Test',
                'body': 'Test',
                'retry_count': 3
            }
            
            consumer.handle_retry(message, 123)
            
            # 验证不再发送到重试队列
            consumer.channel.basic_publish.assert_not_called()
            
            # 验证消息被确认（丢弃）
            consumer.channel.basic_ack.assert_called_once()
    
    def test_retry_preserves_message_content(self):
        """测试重试保留原始消息内容"""
        with patch('services.notification.main.get_rabbitmq_connection'):
            consumer = NotificationConsumer()
            consumer.channel = Mock()
            
            original_message = {
                'type': 'email',
                'to': 'test@example.com',
                'subject': 'Important Message',
                'body': 'This is important',
                'retry_count': 1,
                'custom_field': 'custom_value'
            }
            
            consumer.handle_retry(original_message, 123)
            
            # 获取发布的消息
            call_args = consumer.channel.basic_publish.call_args
            published_message = json.loads(call_args[1]['body'])
            
            # 验证所有字段都保留（除了retry_count增加）
            assert published_message['type'] == 'email'
            assert published_message['to'] == 'test@example.com'
            assert published_message['subject'] == 'Important Message'
            assert published_message['body'] == 'This is important'
            assert published_message['custom_field'] == 'custom_value'
            assert published_message['retry_count'] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
