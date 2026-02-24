"""
角色权限测试

Feature: unified-auth-platform, Property 17-20: 角色权限管理

验证需求：4.2, 4.3, 4.4, 4.5
"""
import pytest
from hypothesis import given, strategies as st
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.models.user import Base
from shared.models.permission import Role, Permission, RolePermission, UserRole
from shared.database import get_db
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.permission.main import app

TEST_DATABASE_URL = "sqlite:///./test_permissions.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

role_names = st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll')), min_size=3, max_size=50)
permission_names = st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll')), min_size=3, max_size=50)

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_role_permission_assignment():
    """测试角色权限分配"""
    # 创建角色
    role_response = client.post("/api/v1/roles", json={"name": "admin", "description": "管理员"})
    assert role_response.status_code == 200
    role_id = role_response.json()["id"]
    
    # 创建权限
    perm_response = client.post("/api/v1/permissions", json={
        "name": "user:create", "resource": "user", "action": "create"
    })
    assert perm_response.status_code == 200
    perm_id = perm_response.json()["id"]
    
    # 分配权限给角色
    assign_response = client.post(f"/api/v1/roles/{role_id}/permissions", json=[perm_id])
    assert assign_response.status_code == 200

def test_user_role_assignment():
    """测试用户角色分配"""
    # 创建角色
    role_response = client.post("/api/v1/roles", json={"name": "user", "description": "普通用户"})
    assert role_response.status_code == 200
    role_id = role_response.json()["id"]
    
    # 分配角色给用户
    user_id = "test-user-123"
    assign_response = client.post(f"/api/v1/users/{user_id}/roles", json=[role_id])
    assert assign_response.status_code == 200

def test_user_permissions_query():
    """测试用户权限查询"""
    # 创建角色
    role_response = client.post("/api/v1/roles", json={"name": "editor", "description": "编辑"})
    role_id = role_response.json()["id"]
    
    # 创建权限
    perm_response = client.post("/api/v1/permissions", json={
        "name": "post:edit", "resource": "post", "action": "edit"
    })
    perm_id = perm_response.json()["id"]
    
    # 分配权限给角色
    client.post(f"/api/v1/roles/{role_id}/permissions", json=[perm_id])
    
    # 分配角色给用户
    user_id = "test-user-456"
    client.post(f"/api/v1/users/{user_id}/roles", json=[role_id])
    
    # 查询用户权限
    perms_response = client.get(f"/api/v1/users/{user_id}/permissions")
    assert perms_response.status_code == 200
    permissions = perms_response.json()["permissions"]
    assert len(permissions) > 0

def test_duplicate_role_name():
    """测试重复角色名"""
    client.post("/api/v1/roles", json={"name": "duplicate", "description": "测试"})
    response = client.post("/api/v1/roles", json={"name": "duplicate", "description": "测试2"})
    assert response.status_code == 409

def test_system_role_protection():
    """测试系统角色保护"""
    # 创建系统角色
    db = TestingSessionLocal()
    try:
        role = Role(name="system_admin", description="系统管理员", is_system_role=True)
        db.add(role)
        db.commit()
        db.refresh(role)
        role_id = str(role.id)
    finally:
        db.close()
    
    # 尝试删除系统角色
    response = client.delete(f"/api/v1/roles/{role_id}")
    assert response.status_code == 403
