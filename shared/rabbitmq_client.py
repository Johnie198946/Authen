"""
RabbitMQ客户端管理
"""
import pika
from shared.config import settings


def get_rabbitmq_connection():
    """获取RabbitMQ连接"""
    parameters = pika.URLParameters(settings.RABBITMQ_URL)
    connection = pika.BlockingConnection(parameters)
    return connection


def get_rabbitmq_channel():
    """获取RabbitMQ通道"""
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    return channel
