"""
邮件发送服务

实现SMTP邮件发送、模板渲染和重试机制。
支持从数据库读取云服务配置和邮件模板。
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from jinja2 import Template, TemplateError
from sqlalchemy.orm import Session
from shared.database import get_db
from shared.models.system import CloudServiceConfig, MessageTemplate

logger = logging.getLogger(__name__)


class EmailService:
    """邮件发送服务"""
    
    def __init__(self):
        """初始化邮件服务"""
        self.smtp_config = None
        self.load_smtp_config()
    
    def load_smtp_config(self) -> bool:
        """
        从数据库加载SMTP配置
        
        Returns:
            是否成功加载配置
        """
        try:
            db = next(get_db())
            try:
                # 查询活跃的邮件服务配置
                config = db.query(CloudServiceConfig).filter(
                    CloudServiceConfig.service_type == 'email',
                    CloudServiceConfig.is_active == True
                ).first()
                
                if config:
                    self.smtp_config = config.config
                    logger.info(f"成功加载SMTP配置: {config.provider}")
                    return True
                else:
                    logger.warning("未找到活跃的邮件服务配置")
                    return False
            finally:
                db.close()
        except Exception as e:
            logger.error(f"加载SMTP配置失败: {e}")
            return False
    
    def get_template(self, template_name: str, db: Session) -> Optional[MessageTemplate]:
        """
        从数据库获取邮件模板
        
        Args:
            template_name: 模板名称
            db: 数据库会话
            
        Returns:
            邮件模板对象，如果不存在则返回None
        """
        try:
            template = db.query(MessageTemplate).filter(
                MessageTemplate.name == template_name,
                MessageTemplate.type == 'email'
            ).first()
            return template
        except Exception as e:
            logger.error(f"获取邮件模板失败: {e}")
            return None
    
    def render_template(self, template_content: str, variables: Dict[str, Any]) -> str:
        """
        渲染邮件模板
        
        Args:
            template_content: 模板内容
            variables: 模板变量
            
        Returns:
            渲染后的内容
            
        Raises:
            TemplateError: 模板渲染失败
        """
        try:
            template = Template(template_content)
            return template.render(**variables)
        except TemplateError as e:
            logger.error(f"模板渲染失败: {e}")
            raise
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        template_name: Optional[str] = None,
        template_variables: Optional[Dict[str, Any]] = None,
        html: bool = True
    ) -> bool:
        """
        发送邮件
        
        Args:
            to_email: 收件人邮箱
            subject: 邮件主题
            body: 邮件正文（如果使用模板，此参数可为空）
            template_name: 可选的模板名称
            template_variables: 模板变量
            html: 是否为HTML邮件
            
        Returns:
            发送是否成功
        """
        # 如果没有配置，尝试重新加载
        if not self.smtp_config:
            if not self.load_smtp_config():
                logger.error("无法发送邮件：未配置SMTP服务")
                return False
        
        try:
            # 如果指定了模板，使用模板渲染
            if template_name:
                db = next(get_db())
                try:
                    template = self.get_template(template_name, db)
                    if template:
                        # 渲染主题和正文
                        if template.subject:
                            subject = self.render_template(
                                template.subject,
                                template_variables or {}
                            )
                        body = self.render_template(
                            template.content,
                            template_variables or {}
                        )
                        logger.info(f"使用模板 '{template_name}' 渲染邮件")
                    else:
                        logger.warning(f"模板 '{template_name}' 不存在，使用原始内容")
                finally:
                    db.close()
            
            # 创建邮件消息
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.smtp_config.get('from_email') or self.smtp_config.get('username')
            msg['To'] = to_email
            
            # 添加邮件正文
            if html:
                msg.attach(MIMEText(body, 'html', 'utf-8'))
            else:
                msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # 连接SMTP服务器并发送
            smtp_host = self.smtp_config.get('smtp_host')
            smtp_port = self.smtp_config.get('smtp_port', 587)
            use_ssl = self.smtp_config.get('use_ssl', False)
            use_tls = self.smtp_config.get('use_tls', True)
            username = self.smtp_config.get('username')
            password = self.smtp_config.get('password')
            
            if not smtp_host or not username or not password:
                logger.error("SMTP配置不完整")
                return False
            
            # 根据配置选择SSL或TLS
            if use_ssl:
                # 使用SSL连接（通常端口465）
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
            else:
                # 使用普通连接，可能需要STARTTLS（通常端口587或25）
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
                if use_tls:
                    server.starttls()
            
            try:
                # 登录
                server.login(username, password)
                
                # 发送邮件
                server.send_message(msg)
                
                logger.info(f"邮件发送成功: {to_email}, 主题: {subject}")
                return True
                
            finally:
                server.quit()
                
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP认证失败: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP错误: {e}")
            return False
        except TemplateError as e:
            logger.error(f"模板渲染错误: {e}")
            return False
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False
    
    def send_verification_email(self, to_email: str, verification_link: str) -> bool:
        """
        发送验证邮件
        
        Args:
            to_email: 收件人邮箱
            verification_link: 验证链接
            
        Returns:
            发送是否成功
        """
        return self.send_email(
            to_email=to_email,
            subject="",  # 将从模板获取
            body="",  # 将从模板获取
            template_name="email_verification",
            template_variables={
                'email': to_email,
                'verification_link': verification_link
            }
        )
    
    def send_password_reset_email(self, to_email: str, reset_link: str) -> bool:
        """
        发送密码重置邮件
        
        Args:
            to_email: 收件人邮箱
            reset_link: 重置链接
            
        Returns:
            发送是否成功
        """
        return self.send_email(
            to_email=to_email,
            subject="",  # 将从模板获取
            body="",  # 将从模板获取
            template_name="password_reset",
            template_variables={
                'email': to_email,
                'reset_link': reset_link
            }
        )
    
    def send_subscription_reminder(
        self,
        to_email: str,
        plan_name: str,
        expiry_date: str
    ) -> bool:
        """
        发送订阅到期提醒邮件
        
        Args:
            to_email: 收件人邮箱
            plan_name: 订阅计划名称
            expiry_date: 到期日期
            
        Returns:
            发送是否成功
        """
        return self.send_email(
            to_email=to_email,
            subject="",  # 将从模板获取
            body="",  # 将从模板获取
            template_name="subscription_reminder",
            template_variables={
                'email': to_email,
                'plan_name': plan_name,
                'expiry_date': expiry_date
            }
        )


# 全局邮件服务实例
email_service = EmailService()
