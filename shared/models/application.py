"""
应用相关数据模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
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


class Application(Base):
    """应用表"""
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    app_id = Column(String(64), unique=True, nullable=False, index=True)
    app_secret_hash = Column(String(255), nullable=False)
    status = Column(String(20), default='active', nullable=False, index=True)  # active / disabled
    rate_limit = Column(Integer, default=60, nullable=False)
    webhook_secret = Column(String(255), nullable=True)  # Webhook 签名密钥
    webhook_url = Column(String(1024), nullable=True)  # Webhook 回调地址
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 关系
    login_methods = relationship("AppLoginMethod", back_populates="application", cascade="all, delete-orphan")
    scopes = relationship("AppScope", back_populates="application", cascade="all, delete-orphan")
    app_users = relationship("AppUser", back_populates="application", cascade="all, delete-orphan")
    app_organizations = relationship("AppOrganization", back_populates="application", cascade="all, delete-orphan")
    app_subscription_plan = relationship("AppSubscriptionPlan", back_populates="application", cascade="all, delete-orphan", uselist=False)
    auto_provision_config = relationship("AutoProvisionConfig", back_populates="application", cascade="all, delete-orphan", uselist=False)


class AppLoginMethod(Base):
    """应用登录方式表"""
    __tablename__ = "app_login_methods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey('applications.id', ondelete='CASCADE'), nullable=False, index=True)
    method = Column(String(20), nullable=False)  # email / phone / wechat / alipay / google / apple
    is_enabled = Column(Boolean, default=True, nullable=False)
    oauth_config = Column(Text, nullable=True)  # 加密存储的 OAuth 配置
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 关系
    application = relationship("Application", back_populates="login_methods")

    __table_args__ = (
        UniqueConstraint('application_id', 'method', name='uq_app_login_method'),
    )


class AppScope(Base):
    """应用权限范围表"""
    __tablename__ = "app_scopes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey('applications.id', ondelete='CASCADE'), nullable=False, index=True)
    scope = Column(String(50), nullable=False)  # user:read / user:write / auth:login / auth:register / role:read / role:write / org:read / org:write
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系
    application = relationship("Application", back_populates="scopes")

    __table_args__ = (
        UniqueConstraint('application_id', 'scope', name='uq_app_scope'),
    )


class AppUser(Base):
    """应用用户绑定表"""
    __tablename__ = "app_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey('applications.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系
    application = relationship("Application", back_populates="app_users")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint('application_id', 'user_id', name='uq_app_user'),
    )


class AppOrganization(Base):
    """应用-组织绑定表"""
    __tablename__ = "app_organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey('applications.id', ondelete='CASCADE'), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    application = relationship("Application", back_populates="app_organizations")

    __table_args__ = (
        UniqueConstraint('application_id', 'organization_id', name='uq_app_organization'),
    )


class AppSubscriptionPlan(Base):
    """应用-订阅计划绑定表"""
    __tablename__ = "app_subscription_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey('applications.id', ondelete='CASCADE'), nullable=False, index=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey('subscription_plans.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    application = relationship("Application", back_populates="app_subscription_plan")

    __table_args__ = (
        UniqueConstraint('application_id', name='uq_app_subscription_plan'),
    )


class AutoProvisionConfig(Base):
    """应用用户自动配置规则表"""
    __tablename__ = "auto_provision_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey('applications.id', ondelete='CASCADE'),
        nullable=False, unique=True, index=True
    )
    role_ids = Column(JSONBCompat, default=list)
    permission_ids = Column(JSONBCompat, default=list)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='SET NULL'),
        nullable=True
    )
    subscription_plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey('subscription_plans.id', ondelete='SET NULL'),
        nullable=True
    )
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    application = relationship("Application", back_populates="auto_provision_config")
