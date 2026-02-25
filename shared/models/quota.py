"""
配额相关数据模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from shared.database import Base


class AppQuotaOverride(Base):
    """应用配额覆盖表 - 管理员手动调整的配额值，优先级高于订阅计划默认值"""
    __tablename__ = "app_quota_overrides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey('applications.id', ondelete='CASCADE'),
        nullable=False,
        unique=True
    )
    request_quota = Column(Integer, nullable=True)    # NULL 表示使用订阅计划默认值
    token_quota = Column(BigInteger, nullable=True)   # NULL 表示使用订阅计划默认值
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    application = relationship("Application")


class QuotaUsage(Base):
    """配额使用记录表 - 每个计费周期结束时持久化的使用记录"""
    __tablename__ = "quota_usages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey('applications.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    billing_cycle_start = Column(DateTime, nullable=False)
    billing_cycle_end = Column(DateTime, nullable=False)
    request_quota_limit = Column(Integer, nullable=False)
    request_quota_used = Column(Integer, nullable=False)
    token_quota_limit = Column(BigInteger, nullable=False)
    token_quota_used = Column(BigInteger, nullable=False)
    reset_type = Column(String(20), nullable=False)  # auto / manual
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    application = relationship("Application")
