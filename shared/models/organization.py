"""
组织架构相关数据模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from shared.database import Base


class Organization(Base):
    """组织架构表"""
    __tablename__ = "organizations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True, index=True)
    path = Column(Text, nullable=False, index=True)  # 完整路径，如 /root/dept1/team1
    level = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系
    children = relationship("Organization", backref="parent", remote_side=[id])
    user_organizations = relationship("UserOrganization", back_populates="organization", cascade="all, delete-orphan")
    organization_permissions = relationship("OrganizationPermission", back_populates="organization", cascade="all, delete-orphan")


class UserOrganization(Base):
    """用户组织关联表"""
    __tablename__ = "user_organizations"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 关系
    user = relationship("User", back_populates="user_organizations")
    organization = relationship("Organization", back_populates="user_organizations")


class OrganizationPermission(Base):
    """组织权限表"""
    __tablename__ = "organization_permissions"
    
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), primary_key=True)
    permission_id = Column(UUID(as_uuid=True), ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 关系
    organization = relationship("Organization", back_populates="organization_permissions")
    permission = relationship("Permission", back_populates="organization_permissions")
