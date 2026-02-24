"""
通知服务 - 消息队列消费者

该服务从RabbitMQ消费消息并发送邮件和短信通知。
支持消息路由和重试机制。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import logging
import time
import pika
from typing import Dict, Any, Optional
from shared.config import settings
from shared.rabbitmq_client import get_rabbitmq_connection
from services.notification.email_service import email_service
from services.notification.sms_service import sms_service

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 队列名称常量
QUEUE_EMAIL = 'notifications.email'
QUEUE_SMS = 'notifications.sms'
QUEUE_RETRY = 'notifications.retry'

# 重试配置
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 60  # 重试延迟（秒）


class NotificationConsumer:
    """通知服务消费者"""
    
    def __init__(self):
        """初始化消费者"""
        self.connection = None
        self.channel = None
        self.setup_connection()
    
    def setup_connection(self):
        """设置RabbitMQ连接和通道"""
        try:
            logger.info("正在连接到RabbitMQ...")
            self.connection = get_rabbitmq_connection()
            self.channel = self.connection.channel()
            
            # 声明队列（持久化）
            self.channel.queue_declare(queue=QUEUE_EMAIL, durable=True)
            self.channel.queue_declare(queue=QUEUE_SMS, durable=True)
            self.channel.queue_declare(queue=QUEUE_RETRY, durable=True)
            
            # 设置QoS（每次只处理一条消息）
            self.channel.basic_qos(prefetch_count=1)
            
            logger.info("RabbitMQ连接成功")
        except Exception as e:
            logger.error(f"RabbitMQ连接失败: {e}")
            raise
    
    def route_message(self, message: Dict[str, Any]) -> bool:
        """
        路由消息到相应的处理器
        
        Args:
            message: 消息内容
            
        Returns:
            处理是否成功
        """
        message_type = message.get('type')
        
        if message_type == 'email':
            return self.send_email(message)
        elif message_type == 'sms':
            return self.send_sms(message)
        else:
            logger.error(f"未知的消息类型: {message_type}")
            return False
    
    def send_email(self, message: Dict[str, Any]) -> bool:
        """
        发送邮件
        
        Args:
            message: 邮件消息内容
                - to: 收件人邮箱
                - subject: 邮件主题
                - body: 邮件正文
                - template: 可选的模板名称
                - template_variables: 可选的模板变量
                - html: 是否为HTML邮件（默认True）
                
        Returns:
            发送是否成功
        """
        try:
            to_email = message.get('to')
            subject = message.get('subject', '')
            body = message.get('body', '')
            template = message.get('template')
            template_variables = message.get('template_variables', {})
            html = message.get('html', True)
            
            if not to_email:
                logger.error(f"邮件消息缺少收件人: {message}")
                return False
            
            # 如果没有模板，必须有主题和正文
            if not template and (not subject or not body):
                logger.error(f"邮件消息缺少必要字段（主题或正文）: {message}")
                return False
            
            logger.info(f"发送邮件到 {to_email}, 主题: {subject or '(使用模板)'}")
            
            # 使用邮件服务发送
            success = email_service.send_email(
                to_email=to_email,
                subject=subject,
                body=body,
                template_name=template,
                template_variables=template_variables,
                html=html
            )
            
            if success:
                logger.info(f"邮件发送成功: {to_email}")
            else:
                logger.error(f"邮件发送失败: {to_email}")
            
            return success
            
        except Exception as e:
            logger.error(f"邮件发送异常: {e}")
            return False
    
    def send_sms(self, message: Dict[str, Any]) -> bool:
        """
        发送短信
        
        Args:
            message: 短信消息内容
                - to: 收件人手机号
                - content: 短信内容
                - template: 可选的模板名称
                - template_variables: 可选的模板变量
                
        Returns:
            发送是否成功
        """
        try:
            to_phone = message.get('to')
            content = message.get('content', '')
            template = message.get('template')
            template_variables = message.get('template_variables', {})
            
            if not to_phone:
                logger.error(f"短信消息缺少收件人: {message}")
                return False
            
            # 如果没有模板，必须有内容
            if not template and not content:
                logger.error(f"短信消息缺少必要字段（内容）: {message}")
                return False
            
            logger.info(f"发送短信到 {to_phone}")
            
            # 使用短信服务发送
            success = sms_service.send_sms(
                to_phone=to_phone,
                content=content,
                template_name=template,
                template_variables=template_variables
            )
            
            if success:
                logger.info(f"短信发送成功: {to_phone}")
            else:
                logger.error(f"短信发送失败: {to_phone}")
            
            return success
            
        except Exception as e:
            logger.error(f"短信发送异常: {e}")
            return False
    
    def handle_retry(self, message: Dict[str, Any], delivery_tag: int):
        """
        处理消息重试
        
        Args:
            message: 原始消息
            delivery_tag: 消息的delivery tag
        """
        retry_count = message.get('retry_count', 0)
        
        if retry_count >= MAX_RETRY_ATTEMPTS:
            logger.error(f"消息重试次数已达上限 ({MAX_RETRY_ATTEMPTS}), 放弃处理: {message}")
            # 确认消息（从队列中移除）
            self.channel.basic_ack(delivery_tag=delivery_tag)
            return
        
        # 增加重试计数
        message['retry_count'] = retry_count + 1
        
        # 发送到重试队列
        logger.info(f"将消息发送到重试队列 (尝试 {message['retry_count']}/{MAX_RETRY_ATTEMPTS})")
        
        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=QUEUE_RETRY,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 持久化消息
                )
            )
            # 确认原消息
            self.channel.basic_ack(delivery_tag=delivery_tag)
        except Exception as e:
            logger.error(f"发送到重试队列失败: {e}")
            # 拒绝消息并重新入队
            self.channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
    
    def process_message(self, ch, method, properties, body):
        """
        处理接收到的消息
        
        Args:
            ch: 通道
            method: 方法
            properties: 消息属性
            body: 消息体
        """
        try:
            # 解析消息
            message = json.loads(body)
            logger.info(f"收到消息: {message}")
            
            # 路由并处理消息
            success = self.route_message(message)
            
            if success:
                # 处理成功，确认消息
                logger.info("消息处理成功")
                ch.basic_ack(delivery_tag=method.delivery_tag)
            else:
                # 处理失败，进入重试流程
                logger.warning("消息处理失败，准备重试")
                self.handle_retry(message, method.delivery_tag)
                
        except json.JSONDecodeError as e:
            logger.error(f"消息JSON解析失败: {e}")
            # 无效的消息格式，直接确认（丢弃）
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.error(f"消息处理异常: {e}")
            # 发生异常，拒绝消息并重新入队
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def process_retry_message(self, ch, method, properties, body):
        """
        处理重试队列中的消息
        
        Args:
            ch: 通道
            method: 方法
            properties: 消息属性
            body: 消息体
        """
        try:
            # 等待一段时间后再重试
            logger.info(f"等待 {RETRY_DELAY_SECONDS} 秒后重试...")
            time.sleep(RETRY_DELAY_SECONDS)
            
            # 解析消息
            message = json.loads(body)
            logger.info(f"重试处理消息: {message}")
            
            # 路由并处理消息
            success = self.route_message(message)
            
            if success:
                # 处理成功，确认消息
                logger.info("重试成功")
                ch.basic_ack(delivery_tag=method.delivery_tag)
            else:
                # 处理失败，继续重试
                logger.warning("重试失败，继续重试流程")
                self.handle_retry(message, method.delivery_tag)
                
        except json.JSONDecodeError as e:
            logger.error(f"重试消息JSON解析失败: {e}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.error(f"重试消息处理异常: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def start_consuming(self):
        """开始消费消息"""
        try:
            logger.info("开始监听消息队列...")
            
            # 订阅邮件队列
            self.channel.basic_consume(
                queue=QUEUE_EMAIL,
                on_message_callback=self.process_message
            )
            
            # 订阅短信队列
            self.channel.basic_consume(
                queue=QUEUE_SMS,
                on_message_callback=self.process_message
            )
            
            # 订阅重试队列
            self.channel.basic_consume(
                queue=QUEUE_RETRY,
                on_message_callback=self.process_retry_message
            )
            
            logger.info(f"正在监听队列: {QUEUE_EMAIL}, {QUEUE_SMS}, {QUEUE_RETRY}")
            logger.info("按 Ctrl+C 停止服务")
            
            # 开始消费
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在关闭...")
            self.stop()
        except Exception as e:
            logger.error(f"消费消息时发生错误: {e}")
            self.stop()
            raise
    
    def stop(self):
        """停止消费者并关闭连接"""
        try:
            if self.channel and self.channel.is_open:
                self.channel.stop_consuming()
                self.channel.close()
            if self.connection and self.connection.is_open:
                self.connection.close()
            logger.info("通知服务已停止")
        except Exception as e:
            logger.error(f"关闭连接时发生错误: {e}")


def main():
    """主函数"""
    logger.info("启动通知服务...")
    logger.info(f"RabbitMQ URL: {settings.RABBITMQ_URL}")
    
    consumer = NotificationConsumer()
    consumer.start_consuming()


if __name__ == "__main__":
    main()
