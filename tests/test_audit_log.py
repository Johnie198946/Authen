"""
审计日志功能测试

测试审计日志记录装饰器和辅助函数的功能。

需求：6.5, 11.9, 13.1, 13.2 - 审计日志记录
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import Request
from unittest.mock import Mock, MagicMock
import uuid

from shared.database import get_db, engine, Base
from shared.models.system import AuditLog
from shared.models.user import User
from shared.utils.audit_log import (
    get_client_ip,
    get_user_agent,
    create_audit_log,
    audit_log,
    log_authentication_event,
    log_admin_operation,
    log_permission_change,
    log_super_admin_operation
)


@pytest.fixture(scope="function")
def db_session():
    """创建测试数据库会话"""
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db_session):
    """创建测试用户"""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def mock_request():
    """创建模拟的FastAPI请求对象"""
    request = Mock(spec=Request)
    request.headers = {
        "User-Agent": "Mozilla/5.0 Test Browser",
        "X-Forwarded-For": "192.168.1.100",
        "X-Real-IP": "192.168.1.100"
    }
    request.client = Mock()
    request.client.host = "192.168.1.100"
    return request


# ==================== 辅助函数测试 ====================

def test_get_client_ip_from_x_forwarded_for(mock_request):
    """测试从X-Forwarded-For头获取IP地址"""
    mock_request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}
    ip = get_client_ip(mock_request)
    assert ip == "203.0.113.1"


def test_get_client_ip_from_x_real_ip(mock_request):
    """测试从X-Real-IP头获取IP地址"""
    mock_request.headers = {"X-Real-IP": "203.0.113.2"}
    ip = get_client_ip(mock_request)
    assert ip == "203.0.113.2"


def test_get_client_ip_from_client(mock_request):
    """测试从客户端直接获取IP地址"""
    mock_request.headers = {}
    mock_request.client.host = "203.0.113.3"
    ip = get_client_ip(mock_request)
    assert ip == "203.0.113.3"


def test_get_client_ip_no_client():
    """测试没有客户端信息时返回None"""
    request = Mock(spec=Request)
    request.headers = {}
    request.client = None
    ip = get_client_ip(request)
    assert ip is None


def test_get_user_agent(mock_request):
    """测试获取用户代理字符串"""
    user_agent = get_user_agent(mock_request)
    assert user_agent == "Mozilla/5.0 Test Browser"


def test_get_user_agent_missing():
    """测试用户代理缺失时返回None"""
    request = Mock(spec=Request)
    request.headers = {}
    user_agent = get_user_agent(request)
    assert user_agent is None


# ==================== 审计日志创建测试 ====================

def test_create_audit_log_basic(db_session, test_user):
    """测试创建基本审计日志"""
    create_audit_log(
        db=db_session,
        user_id=test_user.id,
        action="test_action",
        resource_type="test_resource",
        ip_address="192.168.1.100"
    )
    
    # 验证日志已创建
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id,
        AuditLog.action == "test_action"
    ).first()
    
    assert log is not None
    assert log.action == "test_action"
    assert log.resource_type == "test_resource"
    assert log.ip_address == "192.168.1.100"
    assert log.user_id == test_user.id


def test_create_audit_log_with_details(db_session, test_user):
    """测试创建包含详情的审计日志"""
    details = {
        "field1": "value1",
        "field2": 123,
        "field3": True
    }
    
    create_audit_log(
        db=db_session,
        user_id=test_user.id,
        action="test_action",
        details=details
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id
    ).first()
    
    assert log is not None
    assert log.details == details


def test_create_audit_log_with_resource_id(db_session, test_user):
    """测试创建包含资源ID的审计日志"""
    resource_id = uuid.uuid4()
    
    create_audit_log(
        db=db_session,
        user_id=test_user.id,
        action="test_action",
        resource_type="test_resource",
        resource_id=resource_id
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id
    ).first()
    
    assert log is not None
    assert log.resource_id == resource_id


def test_create_audit_log_without_user(db_session):
    """测试创建没有用户ID的审计日志（匿名操作）"""
    create_audit_log(
        db=db_session,
        user_id=None,
        action="anonymous_action",
        ip_address="192.168.1.100"
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.action == "anonymous_action"
    ).first()
    
    assert log is not None
    assert log.user_id is None
    assert log.ip_address == "192.168.1.100"


def test_create_audit_log_with_user_agent(db_session, test_user):
    """测试创建包含用户代理的审计日志"""
    user_agent = "Mozilla/5.0 Test Browser"
    
    create_audit_log(
        db=db_session,
        user_id=test_user.id,
        action="test_action",
        user_agent=user_agent
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id
    ).first()
    
    assert log is not None
    assert log.user_agent == user_agent


# ==================== 装饰器测试 ====================

def test_audit_log_decorator_async(db_session, test_user, mock_request):
    """测试审计日志装饰器（异步函数）"""
    @audit_log(
        action="test_async_action",
        resource_type="test_resource"
    )
    async def test_async_function(request: Request, user_id: str, db: Session):
        return {"success": True, "user_id": user_id}
    
    # 执行函数
    import asyncio
    result = asyncio.run(test_async_function(
        request=mock_request,
        user_id=str(test_user.id),
        db=db_session
    ))
    
    assert result["success"] is True
    
    # 验证日志已创建
    log = db_session.query(AuditLog).filter(
        AuditLog.action == "test_async_action"
    ).first()
    
    assert log is not None
    assert log.user_id == test_user.id
    assert log.resource_type == "test_resource"
    assert log.ip_address == "192.168.1.100"


def test_audit_log_decorator_sync(db_session, test_user, mock_request):
    """测试审计日志装饰器（同步函数）"""
    @audit_log(
        action="test_sync_action",
        resource_type="test_resource"
    )
    def test_sync_function(request: Request, user_id: str, db: Session):
        return {"success": True, "user_id": user_id}
    
    # 执行函数
    result = test_sync_function(
        request=mock_request,
        user_id=str(test_user.id),
        db=db_session
    )
    
    assert result["success"] is True
    
    # 验证日志已创建
    log = db_session.query(AuditLog).filter(
        AuditLog.action == "test_sync_action"
    ).first()
    
    assert log is not None
    assert log.user_id == test_user.id


def test_audit_log_decorator_with_resource_id(db_session, test_user, mock_request):
    """测试装饰器提取资源ID"""
    resource_id = str(uuid.uuid4())
    
    @audit_log(
        action="test_action",
        resource_type="test_resource",
        get_resource_id=lambda result: result.get("resource_id")
    )
    async def test_function(request: Request, user_id: str, db: Session):
        return {"success": True, "resource_id": resource_id}
    
    import asyncio
    asyncio.run(test_function(
        request=mock_request,
        user_id=str(test_user.id),
        db=db_session
    ))
    
    log = db_session.query(AuditLog).filter(
        AuditLog.action == "test_action"
    ).first()
    
    assert log is not None
    assert str(log.resource_id) == resource_id


def test_audit_log_decorator_with_details(db_session, test_user, mock_request):
    """测试装饰器提取详情"""
    @audit_log(
        action="test_action",
        resource_type="test_resource",
        get_details=lambda kwargs, result: {
            "input_data": kwargs.get("data"),
            "output_data": result.get("output")
        }
    )
    async def test_function(request: Request, user_id: str, db: Session, data: str):
        return {"success": True, "output": "processed_" + data}
    
    import asyncio
    asyncio.run(test_function(
        request=mock_request,
        user_id=str(test_user.id),
        db=db_session,
        data="test_data"
    ))
    
    log = db_session.query(AuditLog).filter(
        AuditLog.action == "test_action"
    ).first()
    
    assert log is not None
    assert log.details["input_data"] == "test_data"
    assert log.details["output_data"] == "processed_test_data"


# ==================== 认证事件日志测试 ====================

def test_log_authentication_event_success(db_session, test_user):
    """测试记录成功的认证事件"""
    log_authentication_event(
        db=db_session,
        user_id=test_user.id,
        action="login",
        success=True,
        ip_address="192.168.1.100",
        details={"method": "password"}
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id,
        AuditLog.action == "login"
    ).first()
    
    assert log is not None
    assert log.resource_type == "authentication"
    assert log.details["success"] is True
    assert log.details["method"] == "password"


def test_log_authentication_event_failure(db_session, test_user):
    """测试记录失败的认证事件"""
    log_authentication_event(
        db=db_session,
        user_id=test_user.id,
        action="login",
        success=False,
        ip_address="192.168.1.100",
        details={"reason": "invalid_password"}
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id,
        AuditLog.action == "login"
    ).first()
    
    assert log is not None
    assert log.details["success"] is False
    assert log.details["reason"] == "invalid_password"


def test_log_authentication_event_logout(db_session, test_user):
    """测试记录登出事件"""
    log_authentication_event(
        db=db_session,
        user_id=test_user.id,
        action="logout",
        success=True,
        ip_address="192.168.1.100"
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id,
        AuditLog.action == "logout"
    ).first()
    
    assert log is not None
    assert log.resource_type == "authentication"


def test_log_authentication_event_register(db_session):
    """测试记录注册事件"""
    user_id = uuid.uuid4()
    
    log_authentication_event(
        db=db_session,
        user_id=user_id,
        action="register",
        success=True,
        ip_address="192.168.1.100",
        details={"method": "email"}
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == user_id,
        AuditLog.action == "register"
    ).first()
    
    assert log is not None
    assert log.details["method"] == "email"


# ==================== 管理操作日志测试 ====================

def test_log_admin_operation_create_user(db_session, test_user):
    """测试记录创建用户的管理操作"""
    new_user_id = uuid.uuid4()
    
    log_admin_operation(
        db=db_session,
        user_id=test_user.id,
        action="create",
        resource_type="user",
        resource_id=new_user_id,
        details={"username": "newuser", "email": "newuser@example.com"},
        ip_address="192.168.1.100"
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id,
        AuditLog.action == "create_user"
    ).first()
    
    assert log is not None
    assert log.resource_type == "user"
    assert log.resource_id == new_user_id
    assert log.details["username"] == "newuser"


def test_log_admin_operation_update_role(db_session, test_user):
    """测试记录更新角色的管理操作"""
    role_id = uuid.uuid4()
    
    log_admin_operation(
        db=db_session,
        user_id=test_user.id,
        action="update",
        resource_type="role",
        resource_id=role_id,
        details={"name": "admin", "permissions_added": ["user:create"]},
        ip_address="192.168.1.100"
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id,
        AuditLog.action == "update_role"
    ).first()
    
    assert log is not None
    assert log.resource_type == "role"
    assert log.resource_id == role_id


def test_log_admin_operation_delete_permission(db_session, test_user):
    """测试记录删除权限的管理操作"""
    permission_id = uuid.uuid4()
    
    log_admin_operation(
        db=db_session,
        user_id=test_user.id,
        action="delete",
        resource_type="permission",
        resource_id=permission_id,
        details={"permission_name": "user:delete"},
        ip_address="192.168.1.100"
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id,
        AuditLog.action == "delete_permission"
    ).first()
    
    assert log is not None
    assert log.resource_type == "permission"


# ==================== 权限变更日志测试 ====================

def test_log_permission_change_assign(db_session, test_user):
    """测试记录分配权限的操作"""
    role_id = uuid.uuid4()
    
    log_permission_change(
        db=db_session,
        user_id=test_user.id,
        action="assign_permission",
        target_type="role",
        target_id=role_id,
        details={"permissions": ["user:create", "user:read"]},
        ip_address="192.168.1.100"
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id,
        AuditLog.action == "assign_permission"
    ).first()
    
    assert log is not None
    assert log.resource_type == "permission_change"
    assert log.resource_id == role_id
    assert log.details["target_type"] == "role"
    assert "user:create" in log.details["permissions"]


def test_log_permission_change_revoke(db_session, test_user):
    """测试记录撤销权限的操作"""
    user_id = uuid.uuid4()
    
    log_permission_change(
        db=db_session,
        user_id=test_user.id,
        action="revoke_permission",
        target_type="user",
        target_id=user_id,
        details={"permissions": ["user:delete"]},
        ip_address="192.168.1.100"
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id,
        AuditLog.action == "revoke_permission"
    ).first()
    
    assert log is not None
    assert log.details["target_type"] == "user"


def test_log_permission_change_organization(db_session, test_user):
    """测试记录组织权限变更"""
    org_id = uuid.uuid4()
    
    log_permission_change(
        db=db_session,
        user_id=test_user.id,
        action="assign_permission",
        target_type="organization",
        target_id=org_id,
        details={"permissions": ["org:manage"]},
        ip_address="192.168.1.100"
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id
    ).first()
    
    assert log is not None
    assert log.details["target_type"] == "organization"


# ==================== 超级管理员操作日志测试 ====================

def test_log_super_admin_operation(db_session, test_user):
    """测试记录超级管理员操作"""
    log_super_admin_operation(
        db=db_session,
        user_id=test_user.id,
        action="system_config_change",
        resource_type="system",
        details={"config_key": "max_login_attempts", "old_value": 5, "new_value": 10},
        ip_address="192.168.1.100"
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id,
        AuditLog.action == "system_config_change"
    ).first()
    
    assert log is not None
    assert log.details["is_super_admin"] is True
    assert log.details["config_key"] == "max_login_attempts"


def test_log_super_admin_create_admin(db_session, test_user):
    """测试记录超级管理员创建管理员"""
    new_admin_id = uuid.uuid4()
    
    log_super_admin_operation(
        db=db_session,
        user_id=test_user.id,
        action="create_admin",
        resource_type="user",
        resource_id=new_admin_id,
        details={"username": "newadmin", "role": "admin"},
        ip_address="192.168.1.100"
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id,
        AuditLog.action == "create_admin"
    ).first()
    
    assert log is not None
    assert log.details["is_super_admin"] is True
    assert log.resource_id == new_admin_id


def test_log_super_admin_all_operations_marked(db_session, test_user):
    """测试所有超级管理员操作都被标记"""
    actions = ["create_user", "delete_user", "modify_permissions", "system_maintenance"]
    
    for action in actions:
        log_super_admin_operation(
            db=db_session,
            user_id=test_user.id,
            action=action,
            ip_address="192.168.1.100"
        )
    
    logs = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id
    ).all()
    
    assert len(logs) == len(actions)
    for log in logs:
        assert log.details["is_super_admin"] is True


# ==================== 边界情况测试 ====================

def test_create_audit_log_handles_db_error(db_session, test_user, capsys):
    """测试数据库错误时审计日志不抛出异常"""
    # 关闭数据库会话以模拟错误
    db_session.close()
    
    # 应该不抛出异常
    create_audit_log(
        db=db_session,
        user_id=test_user.id,
        action="test_action"
    )
    
    # 验证错误被记录到标准输出
    captured = capsys.readouterr()
    assert "审计日志记录失败" in captured.out


def test_audit_log_decorator_without_db(mock_request):
    """测试装饰器在没有数据库会话时不报错"""
    @audit_log(action="test_action")
    async def test_function(request: Request, user_id: str):
        return {"success": True}
    
    import asyncio
    result = asyncio.run(test_function(
        request=mock_request,
        user_id=str(uuid.uuid4())
    ))
    
    assert result["success"] is True


def test_audit_log_decorator_without_request(db_session, test_user):
    """测试装饰器在没有请求对象时仍能记录"""
    @audit_log(action="test_action")
    async def test_function(user_id: str, db: Session):
        return {"success": True}
    
    import asyncio
    asyncio.run(test_function(
        user_id=str(test_user.id),
        db=db_session
    ))
    
    log = db_session.query(AuditLog).filter(
        AuditLog.action == "test_action"
    ).first()
    
    assert log is not None
    assert log.ip_address is None
    assert log.user_agent is None


def test_multiple_audit_logs_same_user(db_session, test_user):
    """测试同一用户的多个审计日志"""
    actions = ["login", "create_user", "update_role", "logout"]
    
    for action in actions:
        log_authentication_event(
            db=db_session,
            user_id=test_user.id,
            action=action,
            success=True,
            ip_address="192.168.1.100"
        )
    
    logs = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id
    ).all()
    
    assert len(logs) == len(actions)
    logged_actions = [log.action for log in logs]
    for action in actions:
        assert action in logged_actions


def test_audit_log_with_complex_details(db_session, test_user):
    """测试包含复杂详情的审计日志"""
    complex_details = {
        "nested": {
            "level1": {
                "level2": "value"
            }
        },
        "list": [1, 2, 3],
        "boolean": True,
        "null": None
    }
    
    create_audit_log(
        db=db_session,
        user_id=test_user.id,
        action="complex_action",
        details=complex_details
    )
    
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == test_user.id
    ).first()
    
    assert log is not None
    assert log.details == complex_details
