"""
通知消息发布器

用于其他服务向通知队列发布消息
"""
import json
import logging
import pika
from typing import Dict, Any, Optional
from shared.rabbitmq_client import get_rabbitmq_channel

logger = logging.getLogger(__name__)

# 队列名称常量
QUEUE_EMAIL = 'notifications.email'
QUEUE_SMS = 'notifications.sms'


def publish_email_notification(
    to: str,
    subject: str,
    body: str,
    template: Optional[str] = None,
    **kwargs
) -> bool:
    """
    发布邮件通知消息到队列
    
    Args:
        to: 收件人邮箱
        subject: 邮件主题
        body: 邮件正文
        template: 可选的模板名称
        **kwargs: 其他自定义字段
        
    Returns:
        发布是否成功
    """
    try:
        message = {
            'type': 'email',
            'to': to,
            'subject': subject,
            'body': body,
            'retry_count': 0
        }
        
        if template:
            message['template'] = template
        
        # 添加其他自定义字段
        message.update(kwargs)
        
        channel = get_rabbitmq_channel()
        
        # 发布消息到邮件队列
        channel.basic_publish(
            exchange='',
            routing_key=QUEUE_EMAIL,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # 持久化消息
                content_type='application/json'
            )
        )
        
        logger.info(f"邮件通知已发布到队列: {to}")
        channel.close()
        return True
        
    except Exception as e:
        logger.error(f"发布邮件通知失败: {e}")
        return False


def publish_sms_notification(
    to: str,
    content: str,
    template: Optional[str] = None,
    **kwargs
) -> bool:
    """
    发布短信通知消息到队列
    
    Args:
        to: 收件人手机号
        content: 短信内容
        template: 可选的模板名称
        **kwargs: 其他自定义字段
        
    Returns:
        发布是否成功
    """
    try:
        message = {
            'type': 'sms',
            'to': to,
            'content': content,
            'retry_count': 0
        }
        
        if template:
            message['template'] = template
        
        # 添加其他自定义字段
        message.update(kwargs)
        
        channel = get_rabbitmq_channel()
        
        # 发布消息到短信队列
        channel.basic_publish(
            exchange='',
            routing_key=QUEUE_SMS,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # 持久化消息
                content_type='application/json'
            )
        )
        
        logger.info(f"短信通知已发布到队列: {to}")
        channel.close()
        return True
        
    except Exception as e:
        logger.error(f"发布短信通知失败: {e}")
        return False


def publish_verification_email(to: str, verification_code: str, username: str = None) -> bool:
    """
    发布邮箱验证邮件
    
    Args:
        to: 收件人邮箱
        verification_code: 验证码
        username: 用户名（可选）
        
    Returns:
        发布是否成功
    """
    subject = "验证您的邮箱地址"
    body = f"""
    您好{f' {username}' if username else ''}，
    
    感谢您注册统一身份认证平台！
    
    您的验证码是: {verification_code}
    
    请在15分钟内完成验证。
    
    如果这不是您的操作，请忽略此邮件。
    
    此致
    统一身份认证平台团队
    """
    
    return publish_email_notification(
        to=to,
        subject=subject,
        body=body,
        template='email_verification',
        verification_code=verification_code,
        username=username
    )


def publish_verification_sms(to: str, verification_code: str) -> bool:
    """
    发布手机验证短信
    
    Args:
        to: 收件人手机号
        verification_code: 验证码
        
    Returns:
        发布是否成功
    """
    content = f"【统一认证平台】您的验证码是: {verification_code}，15分钟内有效。请勿泄露给他人。"
    
    return publish_sms_notification(
        to=to,
        content=content,
        template='sms_verification',
        verification_code=verification_code
    )


def publish_subscription_expiry_reminder(to: str, username: str, days_remaining: int, plan_name: str) -> bool:
    """
    发布订阅到期提醒邮件
    
    Args:
        to: 收件人邮箱
        username: 用户名
        days_remaining: 剩余天数
        plan_name: 订阅计划名称
        
    Returns:
        发布是否成功
    """
    subject = f"您的订阅将在{days_remaining}天后到期"
    body = f"""
    您好 {username}，
    
    您的订阅计划 "{plan_name}" 将在 {days_remaining} 天后到期。
    
    为了避免服务中断，请及时续费。
    
    如有任何问题，请联系我们的客服团队。
    
    此致
    统一身份认证平台团队
    """
    
    return publish_email_notification(
        to=to,
        subject=subject,
        body=body,
        template='subscription_expiry_reminder',
        username=username,
        days_remaining=days_remaining,
        plan_name=plan_name
    )
