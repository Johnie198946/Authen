"""
审计日志查询接口测试

测试审计日志查询接口的功能，包括：
- 日志列表查询
- 多条件过滤（用户ID、操作类型、资源类型、时间范围、IP地址）
- 分页和排序
- 权限验证（只有超级管理员可访问）

需求：7.6 - 提供操作日志查询界面
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from fastapi import Query
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import uuid

from shared.database import Base, get_db
from shared.models.user import User
from shared.models.permission import Role, UserRole
from shared.models.system import AuditLog
from services.admin.main import app

# 创建测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_audit_log_query.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建所有表
Base.metadata.create_all(bind=engine)


def override_get_db():
    """覆盖数据库依赖"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# 简化的超级管理员验证覆盖 - 在测试中直接返回user_id
def override_require_super_admin(user_id: str = Query(..., description="当前用户ID")):
    """在测试环境中，简化超级管理员验证"""
    return user_id


# 导入require_super_admin函数并覆盖
from services.admin.main import require_super_admin
app.dependency_overrides[require_super_admin] = override_require_super_admin

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """设置测试数据库"""
    # 创建所有表
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # 清理数据库
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db():
    """创建测试数据库会话"""
    session = TestingSessionLocal()
    yield session
    # 清理测试数据
    session.query(AuditLog).delete()
    session.query(UserRole).delete()
    session.query(User).delete()
    session.query(Role).delete()
    session.commit()
    session.close()


@pytest.fixture
def super_admin_user(db):
    """创建超级管理员用户"""
    # 创建超级管理员角色
    super_admin_role = Role(
        name="super_admin",
        description="超级管理员",
        is_system_role=True
    )
    db.add(super_admin_role)
    db.commit()
    
    # 创建超级管理员用户
    admin_user = User(
        username="admin",
        email="admin@example.com",
        password_hash="hashed_password",
        status="active"
    )
    db.add(admin_user)
    db.commit()
    
    # 分配超级管理员角色
    user_role = UserRole(
        user_id=admin_user.id,
        role_id=super_admin_role.id
    )
    db.add(user_role)
    db.commit()
    
    return admin_user


@pytest.fixture
def regular_user(db):
    """创建普通用户"""
    user = User(
        username="regular_user",
        email="user@example.com",
        password_hash="hashed_password",
        status="active"
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def sample_audit_logs(db, super_admin_user, regular_user):
    """创建示例审计日志"""
    logs = []
    
    # 创建不同类型的日志
    base_time = datetime.utcnow() - timedelta(days=10)
    
    # 登录日志
    for i in range(5):
        log = AuditLog(
            user_id=regular_user.id,
            action="login",
            resource_type="authentication",
            details={"success": True},
            ip_address=f"192.168.1.{i+1}",
            user_agent="Mozilla/5.0",
            created_at=base_time + timedelta(days=i)
        )
        db.add(log)
        logs.append(log)
    
    # 创建用户日志
    for i in range(3):
        log = AuditLog(
            user_id=super_admin_user.id,
            action="create_user",
            resource_type="user",
            resource_id=uuid.uuid4(),
            details={"username": f"user{i}"},
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            created_at=base_time + timedelta(days=i+5)
        )
        db.add(log)
        logs.append(log)
    
    # 权限变更日志
    for i in range(2):
        log = AuditLog(
            user_id=super_admin_user.id,
            action="assign_permission",
            resource_type="permission_change",
            resource_id=uuid.uuid4(),
            details={"target_type": "role"},
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            created_at=base_time + timedelta(days=i+8)
        )
        db.add(log)
        logs.append(log)
    
    db.commit()
    return logs


class TestAuditLogQuery:
    """审计日志查询接口测试"""
    
    def test_list_audit_logs_success(self, db, super_admin_user, sample_audit_logs):
        """测试成功查询审计日志列表"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "logs" in data
        assert data["total"] >= 5  # 至少有5条日志（super_admin创建的）
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["logs"]) >= 5
    
    def test_list_audit_logs_without_super_admin(self, db, regular_user):
        """测试非超级管理员无法访问"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={"user_id": str(regular_user.id)}
        )
        
        assert response.status_code == 403
        assert "只有超级管理员可以访问此接口" in response.json()["detail"]
    
    def test_filter_by_user_id(self, db, super_admin_user, regular_user, sample_audit_logs):
        """测试按用户ID过滤"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "user_id_filter": str(regular_user.id)
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 5  # regular_user有5条登录日志
        for log in data["logs"]:
            assert log["user_id"] == str(regular_user.id)
    
    def test_filter_by_action(self, db, super_admin_user, sample_audit_logs):
        """测试按操作类型过滤"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "action": "create_user"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 3  # 3条创建用户日志
        for log in data["logs"]:
            assert log["action"] == "create_user"
    
    def test_filter_by_resource_type(self, db, super_admin_user, sample_audit_logs):
        """测试按资源类型过滤"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "resource_type": "authentication"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 5  # 5条认证日志
        for log in data["logs"]:
            assert log["resource_type"] == "authentication"
    
    def test_filter_by_time_range(self, db, super_admin_user, sample_audit_logs):
        """测试按时间范围过滤"""
        base_time = datetime.utcnow() - timedelta(days=10)
        start_date = (base_time + timedelta(days=5)).isoformat()
        end_date = (base_time + timedelta(days=8)).isoformat()
        
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "start_date": start_date,
                "end_date": end_date
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 应该有3条日志（day 5, 6, 7）
        assert data["total"] >= 3
        
        # 验证所有日志都在时间范围内
        for log in data["logs"]:
            log_time = datetime.fromisoformat(log["created_at"].replace("Z", "+00:00"))
            assert log_time >= datetime.fromisoformat(start_date)
            assert log_time <= datetime.fromisoformat(end_date)
    
    def test_filter_by_ip_address(self, db, super_admin_user, sample_audit_logs):
        """测试按IP地址过滤"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "ip_address": "192.168.1.100"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 5  # 5条来自192.168.1.100的日志
        for log in data["logs"]:
            assert log["ip_address"] == "192.168.1.100"
    
    def test_pagination(self, db, super_admin_user, sample_audit_logs):
        """测试分页功能"""
        # 第一页
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "page": 1,
                "page_size": 5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 10
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert len(data["logs"]) == 5
        
        # 第二页
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "page": 2,
                "page_size": 5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 10
        assert data["page"] == 2
        assert data["page_size"] == 5
        assert len(data["logs"]) == 5
    
    def test_sort_order_desc(self, db, super_admin_user, sample_audit_logs):
        """测试降序排序（默认）"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "sort_order": "desc"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 验证日志按时间降序排列
        logs = data["logs"]
        for i in range(len(logs) - 1):
            time1 = datetime.fromisoformat(logs[i]["created_at"].replace("Z", "+00:00"))
            time2 = datetime.fromisoformat(logs[i+1]["created_at"].replace("Z", "+00:00"))
            assert time1 >= time2
    
    def test_sort_order_asc(self, db, super_admin_user, sample_audit_logs):
        """测试升序排序"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "sort_order": "asc"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 验证日志按时间升序排列
        logs = data["logs"]
        for i in range(len(logs) - 1):
            time1 = datetime.fromisoformat(logs[i]["created_at"].replace("Z", "+00:00"))
            time2 = datetime.fromisoformat(logs[i+1]["created_at"].replace("Z", "+00:00"))
            assert time1 <= time2
    
    def test_multiple_filters(self, db, super_admin_user, sample_audit_logs):
        """测试多条件组合过滤"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "user_id_filter": str(super_admin_user.id),
                "action": "create_user",
                "resource_type": "user",
                "ip_address": "192.168.1.100"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 3  # 3条符合所有条件的日志
        for log in data["logs"]:
            assert log["user_id"] == str(super_admin_user.id)
            assert log["action"] == "create_user"
            assert log["resource_type"] == "user"
            assert log["ip_address"] == "192.168.1.100"
    
    def test_invalid_user_id_format(self, db, super_admin_user):
        """测试无效的用户ID格式"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "user_id_filter": "invalid-uuid"
            }
        )
        
        assert response.status_code == 422
        assert "无效的用户ID格式" in response.json()["detail"]
    
    def test_invalid_sort_order(self, db, super_admin_user):
        """测试无效的排序顺序"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "sort_order": "invalid"
            }
        )
        
        assert response.status_code == 422
    
    def test_page_size_limits(self, db, super_admin_user, sample_audit_logs):
        """测试分页大小限制"""
        # 测试最小值
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "page_size": 1
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) == 1
        
        # 测试最大值
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "page_size": 100
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) == 10  # 总共只有10条
        
        # 测试超过最大值
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "page_size": 101
            }
        )
        
        assert response.status_code == 422
    
    def test_empty_result(self, db, super_admin_user, sample_audit_logs):
        """测试空结果"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "action": "nonexistent_action"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 0
        assert len(data["logs"]) == 0
    
    def test_log_details_structure(self, db, super_admin_user, sample_audit_logs):
        """测试日志详情结构"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "page_size": 1
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["logs"]) > 0
        log = data["logs"][0]
        
        # 验证日志结构
        assert "id" in log
        assert "user_id" in log
        assert "action" in log
        assert "resource_type" in log
        assert "resource_id" in log
        assert "details" in log
        assert "ip_address" in log
        assert "user_agent" in log
        assert "created_at" in log
        
        # 验证ID格式
        assert uuid.UUID(log["id"])
        if log["user_id"]:
            assert uuid.UUID(log["user_id"])
        if log["resource_id"]:
            assert uuid.UUID(log["resource_id"])


class TestAuditLogQueryEdgeCases:
    """审计日志查询边界情况测试"""
    
    def test_query_with_null_user_id(self, db, super_admin_user):
        """测试查询user_id为NULL的日志"""
        # 创建一个没有用户ID的日志（系统操作）
        log = AuditLog(
            user_id=None,
            action="system_maintenance",
            resource_type="system",
            details={"task": "cleanup"},
            ip_address="127.0.0.1",
            user_agent="System"
        )
        db.add(log)
        db.commit()
        
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 应该能找到这条日志
        system_logs = [l for l in data["logs"] if l["user_id"] is None]
        assert len(system_logs) > 0
    
    def test_query_with_null_ip_address(self, db, super_admin_user):
        """测试查询IP地址为NULL的日志"""
        # 创建一个没有IP地址的日志
        log = AuditLog(
            user_id=super_admin_user.id,
            action="internal_operation",
            resource_type="system",
            details={"source": "internal"},
            ip_address=None,
            user_agent="Internal"
        )
        db.add(log)
        db.commit()
        
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 应该能找到这条日志
        internal_logs = [l for l in data["logs"] if l["ip_address"] is None]
        assert len(internal_logs) > 0
    
    def test_query_with_complex_details(self, db, super_admin_user):
        """测试查询包含复杂details的日志"""
        # 创建一个包含复杂details的日志
        complex_details = {
            "operation": "bulk_update",
            "affected_users": [str(uuid.uuid4()) for _ in range(5)],
            "changes": {
                "field1": {"old": "value1", "new": "value2"},
                "field2": {"old": 100, "new": 200}
            },
            "metadata": {
                "duration_ms": 1234,
                "success_count": 5,
                "failure_count": 0
            }
        }
        
        log = AuditLog(
            user_id=super_admin_user.id,
            action="bulk_update_users",
            resource_type="user",
            details=complex_details,
            ip_address="192.168.1.1",
            user_agent="Admin Tool"
        )
        db.add(log)
        db.commit()
        
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "action": "bulk_update_users"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 1
        log_data = data["logs"][0]
        assert log_data["details"] == complex_details
    
    def test_query_large_page_number(self, db, super_admin_user, sample_audit_logs):
        """测试查询超大页码"""
        response = client.get(
            "/api/v1/admin/audit-logs",
            params={
                "user_id": str(super_admin_user.id),
                "page": 1000,
                "page_size": 20
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 应该返回空结果
        assert data["total"] == 10
        assert len(data["logs"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
