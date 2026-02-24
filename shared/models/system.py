"""
系统配置和日志相关数据模型
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.types import TypeDecorator, JSON
from sqlalchemy.orm import relationship
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


# 创建一个兼容SQLite的INET类型
class INETCompat(TypeDecorator):
    """兼容SQLite的INET类型"""
    impl = String
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(INET())
        else:
            return dialect.type_descriptor(String(45))  # IPv6最长45字符


class CloudServiceConfig(Base):
    """云服务配置表"""
    __tablename__ = "cloud_service_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_type = Column(String(50), nullable=False)  # email, sms
    provider = Column(String(50), nullable=False)  # aliyun, tencent, aws
    config = Column(JSONBCompat, nullable=False)  # 加密存储的配置信息
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class MessageTemplate(Base):
    """消息模板表"""
    __tablename__ = "message_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    type = Column(String(20), nullable=False)  # email, sms
    subject = Column(String(255), nullable=True)  # 仅用于邮件
    content = Column(Text, nullable=False)
    variables = Column(JSONBCompat, nullable=True)  # 模板变量说明
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AuditLog(Base):
    """审计日志表"""
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)  # login, logout, create_user, etc.
    resource_type = Column(String(50), nullable=True)  # user, role, permission, etc.
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(JSONBCompat, nullable=True)
    ip_address = Column(INETCompat, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # 关系
    user = relationship("User", back_populates="audit_logs")


class APILog(Base):
    """API调用日志表"""
    __tablename__ = "api_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    method = Column(String(10), nullable=False)  # GET, POST, PUT, DELETE, etc.
    path = Column(String(500), nullable=False, index=True)
    query_params = Column(JSONBCompat, nullable=True)
    request_body = Column(JSONBCompat, nullable=True)
    status_code = Column(String(3), nullable=False, index=True)
    response_time = Column(String(20), nullable=True)  # 响应时间（毫秒）
    ip_address = Column(INETCompat, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # 关系
    user = relationship("User", foreign_keys=[user_id])
