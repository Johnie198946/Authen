"""
Webhook 事件日志数据模型
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import TypeDecorator, JSON
from sqlalchemy.dialects.postgresql import JSONB
import uuid
from shared.database import Base


# 创建一个兼容SQLite的JSONB类型
class JSONBCompat(TypeDecorator):
    """兼容SQLite的JSONB类型"""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSONB())
        else:
            return dialect.type_descriptor(JSON())


class WebhookEventLog(Base):
    """Webhook 事件日志表"""
    __tablename__ = "webhook_event_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(255), unique=True, nullable=False, index=True)  # 幂等键
    app_id = Column(String(64), nullable=False, index=True)  # 来源应用的 app_id
    event_type = Column(String(50), nullable=False, index=True)  # subscription.created 等
    status = Column(String(20), default='pending', nullable=False, index=True)  # pending/success/failed/duplicate
    request_summary = Column(JSONBCompat, nullable=True)  # 请求体摘要
    response_summary = Column(JSONBCompat, nullable=True)  # 处理结果摘要
    error_message = Column(Text, nullable=True)  # 错误信息
    processed_at = Column(DateTime, nullable=True)  # 处理完成时间
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
