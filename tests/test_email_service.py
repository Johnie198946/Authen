"""
邮件服务单元测试

测试SMTP邮件发送、模板渲染和错误处理。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import uuid
from unittest.mock import Mock, patch, MagicMock
from services.notification.email_service import EmailService
from shared.models.system import CloudServiceConfig, MessageTemplate
from jinja2 import TemplateError


@pytest.fixture
def email_service():
    """创建邮件服务实例"""
    service = EmailService()
    # 设置测试SMTP配置
    service.smtp_config = {
        'smtp_host': 'smtp.example.com',
        'smtp_port': 587,
        'use_ssl': False,
        'use_tls': True,
        'username': 'test@example.com',
        'password': 'testpass',
        'from_email': 'noreply@example.com'
    }
    return service


@pytest.fixture
def mock_db():
    """创建模拟数据库会话"""
    db = Mock()
    return db


class TestEmailService:
    """邮件服务测试类"""
    
    def test_render_template_success(self, email_service):
        """测试模板渲染成功"""
        template_content = "Hello {{ name }}, your code is {{ code }}"
        variables = {'name': 'John', 'code': '123456'}
        
        result = email_service.render_template(template_content, variables)
        
        assert result == "Hello John, your code is 123456"
    
    def test_render_template_with_html(self, email_service):
        """测试HTML模板渲染"""
        template_content = "<h1>Welcome {{ username }}</h1><p>Click <a href='{{ link }}'>here</a></p>"
        variables = {'username': 'Alice', 'link': 'https://example.com/verify'}
        
        result = email_service.render_template(template_content, variables)
        
        assert '<h1>Welcome Alice</h1>' in result
        assert 'https://example.com/verify' in result
    
    def test_render_template_missing_variable(self, email_service):
        """测试模板变量缺失时的处理"""
        template_content = "Hello {{ name }}, your code is {{ code }}"
        variables = {'name': 'John'}  # 缺少 code 变量
        
        # Jinja2会将缺失的变量渲染为空字符串
        result = email_service.render_template(template_content, variables)
        
        assert "Hello John, your code is" in result
    
    def test_render_template_invalid_syntax(self, email_service):
        """测试无效的模板语法"""
        template_content = "Hello {{ name"  # 缺少闭合括号
        variables = {'name': 'John'}
        
        with pytest.raises(TemplateError):
            email_service.render_template(template_content, variables)
    
    @patch('services.notification.email_service.smtplib.SMTP')
    def test_send_email_success(self, mock_smtp, email_service):
        """测试邮件发送成功"""
        # 配置mock
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # 发送邮件
        result = email_service.send_email(
            to_email='recipient@example.com',
            subject='Test Subject',
            body='Test Body',
            html=False
        )
        
        # 验证结果
        assert result is True
        mock_smtp.assert_called_once_with('smtp.example.com', 587, timeout=30)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with('test@example.com', 'testpass')
        mock_server.send_message.assert_called_once()
        mock_server.quit.assert_called_once()
    
    @patch('services.notification.email_service.smtplib.SMTP_SSL')
    def test_send_email_with_ssl(self, mock_smtp_ssl, email_service):
        """测试使用SSL发送邮件"""
        # 修改配置为SSL
        email_service.smtp_config['use_ssl'] = True
        email_service.smtp_config['smtp_port'] = 465
        
        # 配置mock
        mock_server = MagicMock()
        mock_smtp_ssl.return_value = mock_server
        
        # 发送邮件
        result = email_service.send_email(
            to_email='recipient@example.com',
            subject='Test Subject',
            body='Test Body'
        )
        
        # 验证结果
        assert result is True
        mock_smtp_ssl.assert_called_once_with('smtp.example.com', 465, timeout=30)
        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()
    
    @patch('services.notification.email_service.smtplib.SMTP')
    def test_send_email_html(self, mock_smtp, email_service):
        """测试发送HTML邮件"""
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        html_body = '<h1>Test</h1><p>This is a test email</p>'
        
        result = email_service.send_email(
            to_email='recipient@example.com',
            subject='Test HTML',
            body=html_body,
            html=True
        )
        
        assert result is True
        mock_server.send_message.assert_called_once()
    
    @patch('services.notification.email_service.smtplib.SMTP')
    def test_send_email_authentication_failure(self, mock_smtp, email_service):
        """测试SMTP认证失败"""
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        mock_server.login.side_effect = Exception("Authentication failed")
        
        result = email_service.send_email(
            to_email='recipient@example.com',
            subject='Test',
            body='Test'
        )
        
        assert result is False
    
    def test_send_email_no_config(self):
        """测试没有SMTP配置时发送邮件"""
        service = EmailService()
        service.smtp_config = None
        
        with patch.object(service, 'load_smtp_config', return_value=False):
            result = service.send_email(
                to_email='recipient@example.com',
                subject='Test',
                body='Test'
            )
        
        assert result is False
    
    def test_send_email_incomplete_config(self, email_service):
        """测试SMTP配置不完整"""
        # 移除必要的配置项
        del email_service.smtp_config['smtp_host']
        
        result = email_service.send_email(
            to_email='recipient@example.com',
            subject='Test',
            body='Test'
        )
        
        assert result is False
    
    @patch('services.notification.email_service.get_db')
    @patch('services.notification.email_service.smtplib.SMTP')
    def test_send_email_with_template(self, mock_smtp, mock_get_db, email_service):
        """测试使用模板发送邮件"""
        # 配置mock数据库
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        
        # 创建模拟模板
        mock_template = MessageTemplate(
            id=uuid.uuid4(),
            name='test_template',
            type='email',
            subject='Welcome {{ username }}',
            content='<h1>Hello {{ username }}</h1><p>Your code is {{ code }}</p>',
            variables={'username': 'string', 'code': 'string'}
        )
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_template
        
        # 配置SMTP mock
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # 发送邮件
        result = email_service.send_email(
            to_email='recipient@example.com',
            subject='',  # 将从模板获取
            body='',  # 将从模板获取
            template_name='test_template',
            template_variables={'username': 'Alice', 'code': '123456'}
        )
        
        assert result is True
        mock_server.send_message.assert_called_once()
    
    @patch('services.notification.email_service.get_db')
    @patch('services.notification.email_service.smtplib.SMTP')
    def test_send_email_template_not_found(self, mock_smtp, mock_get_db, email_service):
        """测试模板不存在时的处理"""
        # 配置mock数据库
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # 配置SMTP mock
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # 发送邮件（使用不存在的模板，但提供了原始内容）
        result = email_service.send_email(
            to_email='recipient@example.com',
            subject='Test',
            body='Test Body',
            template_name='nonexistent_template'
        )
        
        # 应该使用原始内容发送
        assert result is True
    
    @patch('services.notification.email_service.get_db')
    @patch('services.notification.email_service.smtplib.SMTP')
    def test_send_verification_email(self, mock_smtp, mock_get_db, email_service):
        """测试发送验证邮件"""
        # 配置mock
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        
        mock_template = MessageTemplate(
            id=uuid.uuid4(),
            name='email_verification',
            type='email',
            subject='Verify your email',
            content='Click here: {{ verification_link }}',
            variables={}
        )
        mock_db.query.return_value.filter.return_value.first.return_value = mock_template
        
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # 发送验证邮件
        result = email_service.send_verification_email(
            to_email='user@example.com',
            verification_link='https://example.com/verify?token=abc123'
        )
        
        assert result is True
    
    @patch('services.notification.email_service.get_db')
    @patch('services.notification.email_service.smtplib.SMTP')
    def test_send_password_reset_email(self, mock_smtp, mock_get_db, email_service):
        """测试发送密码重置邮件"""
        # 配置mock
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        
        mock_template = MessageTemplate(
            id=uuid.uuid4(),
            name='password_reset',
            type='email',
            subject='Reset your password',
            content='Reset link: {{ reset_link }}',
            variables={}
        )
        mock_db.query.return_value.filter.return_value.first.return_value = mock_template
        
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # 发送密码重置邮件
        result = email_service.send_password_reset_email(
            to_email='user@example.com',
            reset_link='https://example.com/reset?token=xyz789'
        )
        
        assert result is True
    
    @patch('services.notification.email_service.get_db')
    @patch('services.notification.email_service.smtplib.SMTP')
    def test_send_subscription_reminder(self, mock_smtp, mock_get_db, email_service):
        """测试发送订阅到期提醒"""
        # 配置mock
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        
        mock_template = MessageTemplate(
            id=uuid.uuid4(),
            name='subscription_reminder',
            type='email',
            subject='Subscription expiring soon',
            content='Plan: {{ plan_name }}, Expires: {{ expiry_date }}',
            variables={}
        )
        mock_db.query.return_value.filter.return_value.first.return_value = mock_template
        
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        # 发送订阅提醒
        result = email_service.send_subscription_reminder(
            to_email='user@example.com',
            plan_name='Premium Plan',
            expiry_date='2024-12-31'
        )
        
        assert result is True
    
    @patch('services.notification.email_service.get_db')
    def test_load_smtp_config_success(self, mock_get_db):
        """测试成功加载SMTP配置"""
        service = EmailService()
        service.smtp_config = None
        
        # 配置mock
        mock_db = Mock()
        mock_config = CloudServiceConfig(
            id=uuid.uuid4(),
            service_type='email',
            provider='gmail',
            config={
                'smtp_host': 'smtp.gmail.com',
                'smtp_port': 587,
                'username': 'test@gmail.com',
                'password': 'testpass'
            },
            is_active=True
        )
        
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.first.return_value = mock_config
        
        result = service.load_smtp_config()
        
        assert result is True
        assert service.smtp_config is not None
        assert service.smtp_config['smtp_host'] == 'smtp.gmail.com'
    
    @patch('services.notification.email_service.get_db')
    def test_load_smtp_config_not_found(self, mock_get_db):
        """测试SMTP配置不存在"""
        service = EmailService()
        service.smtp_config = None
        
        # 配置mock
        mock_db = Mock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        result = service.load_smtp_config()
        
        assert result is False
        assert service.smtp_config is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
