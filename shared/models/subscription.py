"""
订阅相关数据模型
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, Boolean, ForeignKey, Text, Numeric, UniqueConstraint
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


class SubscriptionPlan(Base):
    """订阅计划表"""
    __tablename__ = "subscription_plans"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    duration_days = Column(Integer, nullable=False)  # 订阅周期（天）
    price = Column(Numeric(10, 2), nullable=False)
    features = Column(JSONBCompat, nullable=True)  # 订阅包含的功能特性
    is_active = Column(Boolean, default=True, nullable=False)
    request_quota = Column(Integer, default=-1, nullable=False)       # 每周期最大请求次数，-1 表示无限制
    token_quota = Column(BigInteger, default=-1, nullable=False)      # 每周期最大 Token 消耗量，-1 表示无限制
    quota_period_days = Column(Integer, default=30, nullable=False)   # 配额重置周期（天）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系
    user_subscriptions = relationship("UserSubscription", back_populates="plan")
    organization_subscriptions = relationship("OrganizationSubscription", back_populates="plan")
    organization_subscription_requests = relationship(
        "OrganizationSubscriptionRequest", back_populates="target_plan"
    )
    knowledge_pack_policies = relationship(
        "PlanKnowledgePackPolicy", back_populates="plan", cascade="all, delete-orphan"
    )


class UserSubscription(Base):
    """用户订阅表"""
    __tablename__ = "user_subscriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey('subscription_plans.id'), nullable=False)
    status = Column(String(20), default='active', nullable=False, index=True)  # active, expired, cancelled
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False, index=True)
    auto_renew = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系
    user = relationship("User", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="user_subscriptions")


class OrganizationSubscription(Base):
    """组织在指定应用下的套餐，是共享租户知识权益的唯一计费真源。"""
    __tablename__ = "organization_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id = Column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id = Column(
        UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False, index=True
    )
    status = Column(String(20), default="active", nullable=False, index=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False, index=True)
    auto_renew = Column(Boolean, default=True, nullable=False)
    entitlement_version = Column(BigInteger, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    plan = relationship("SubscriptionPlan", back_populates="organization_subscriptions")
    knowledge_grants = relationship(
        "OrganizationKnowledgeGrant", back_populates="subscription", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "application_id", name="uq_org_subscription_app"),
    )


class KnowledgePack(Base):
    """Governed yellow-knowledge product; never represents red tenant content."""
    __tablename__ = "knowledge_packs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entitlement_key = Column(String(120), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="", nullable=False)
    status = Column(String(20), default="draft", nullable=False, index=True)
    is_selectable = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    minimum_document_count = Column(Integer, default=5, nullable=False)
    approved_document_count = Column(Integer, default=0, nullable=False)
    freshness_percent = Column(Integer, default=0, nullable=False)
    risk_label = Column(String(80), default="黄色受限知识", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    grants = relationship("OrganizationKnowledgeGrant", back_populates="knowledge_pack")

    __table_args__ = (
        UniqueConstraint("application_id", "entitlement_key", name="uq_knowledge_pack_app_key"),
    )


class PlanKnowledgePackPolicy(Base):
    """Per-application pack allowance for a subscription plan."""
    __tablename__ = "plan_knowledge_pack_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(
        UUID(as_uuid=True), ForeignKey("subscription_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id = Column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    max_pack_count = Column(Integer, default=0, nullable=False)
    selectable_pack_ids = Column(JSONBCompat, default=list, nullable=False)
    custom_only = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    plan = relationship("SubscriptionPlan", back_populates="knowledge_pack_policies")

    __table_args__ = (
        UniqueConstraint("plan_id", "application_id", name="uq_plan_pack_policy_app"),
    )


class OrganizationKnowledgeGrant(Base):
    """Auditable grant of one governed yellow pack to one organization subscription."""
    __tablename__ = "organization_knowledge_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organization_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_pack_id = Column(
        UUID(as_uuid=True), ForeignKey("knowledge_packs.id"), nullable=False, index=True
    )
    status = Column(String(20), default="active", nullable=False, index=True)
    effective_from = Column(DateTime, nullable=False)
    effective_until = Column(DateTime, nullable=False, index=True)
    approved_by = Column(String(64), default="", nullable=False)
    source_request_id = Column(String(160), default="", nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    subscription = relationship("OrganizationSubscription", back_populates="knowledge_grants")
    knowledge_pack = relationship("KnowledgePack", back_populates="grants")

    __table_args__ = (
        UniqueConstraint(
            "organization_subscription_id", "knowledge_pack_id", name="uq_org_subscription_pack_grant"
        ),
    )


class OrganizationSubscriptionRequest(Base):
    """Idempotent plan-and-pack request awaiting a platform-admin decision."""
    __tablename__ = "organization_subscription_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(String(160), unique=True, nullable=False, index=True)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id = Column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_plan_id = Column(
        UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False, index=True
    )
    requested_by = Column(String(64), nullable=False)
    requested_pack_ids = Column(JSONBCompat, default=list, nullable=False)
    requested_entitlements = Column(JSONBCompat, default=list, nullable=False)
    reason = Column(Text, default="", nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    reviewed_by = Column(String(64), default="", nullable=False)
    review_note = Column(Text, default="", nullable=False)
    approved_pack_ids = Column(JSONBCompat, default=list, nullable=False)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    target_plan = relationship("SubscriptionPlan", back_populates="organization_subscription_requests")
