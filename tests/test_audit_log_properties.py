"""
审计日志属性测试

使用基于属性的测试（Property-Based Testing）验证审计日志系统的正确性。

Feature: unified-auth-platform, Property 35: 综合审计日志记录

对于任意敏感操作（用户认证、管理操作、权限变更、超级管理员操作），
系统应该记录详细的审计日志，包括操作者、操作类型、操作时间、IP地址和操作详情。

**Validates: Requirements 6.5, 9.8, 11.9, 13.1, 13.2**

需求说明：
- 6.5: 记录超级管理员的所有操作日志
- 9.8: 记录所有API调用日志
- 11.9: 记录所有敏感操作的审计日志
- 13.1: 记录所有用户认证事件（成功/失败）
- 13.2: 记录所有管理操作（创建、修改、删除）
"""
import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import Request
from unittest.mock import Mock
import uuid
import json

from shared.database import get_db, engine, Base
from shared.models.system import AuditLog
from shared.models.user import User
from shared.utils.audit_log import (
    create_audit_log,
    log_authentication_event,
    log_admin_operation,
    log_permission_change,
    log_super_admin_operation,
    get_client_ip,
    get_user_agent
)


# ==================== 测试配置 ====================

# 配置Hypothesis
settings.register_profile("default",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile("default")


# ==================== Fixtures ====================

@pytest.fixture(scope="function")
def db_session():
    """创建测试数据库会话"""
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        yield db
        # 清理测试数据
        db.query(AuditLog).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


# ==================== 策略生成器 ====================

# 用户ID生成器
user_ids = st.uuids()

# 操作类型生成器
authentication_actions = st.sampled_from([
    "login", "logout", "register", "password_reset", 
    "email_verification", "phone_verification"
])

admin_actions = st.sampled_from([
    "create", "update", "delete", "read"
])

resource_types = st.sampled_from([
    "user", "role", "permission", "organization", 
    "subscription", "config", "template"
])

permission_actions = st.sampled_from([
    "assign_permission", "revoke_permission", 
    "update_role_permissions", "update_org_permissions"
])

super_admin_actions = st.sampled_from([
    "create_admin", "delete_admin", "system_config_change",
    "database_backup", "system_maintenance", "security_audit"
])

# IP地址生成器
ip_addresses = st.one_of(
    st.ip_addresses(v=4).map(str),
    st.ip_addresses(v=6).map(str),
    st.none()
)

# 用户代理生成器
user_agents = st.one_of(
    st.sampled_from([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
        "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X)",
        "PostmanRuntime/7.26.8",
        "curl/7.68.0"
    ]),
    st.none()
)

# 详情生成器（JSON对象）
details_strategy = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(max_size=100)
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll'))),
            children,
            max_size=5
        )
    ),
    max_leaves=10
)


# ==================== 属性测试 ====================


@given(
    user_id=user_ids,
    action=authentication_actions,
    success=st.booleans(),
    ip_address=ip_addresses,
    user_agent=user_agents,
    details=details_strategy
)
def test_property_authentication_events_are_logged(
    db_session,
    user_id,
    action,
    success,
    ip_address,
    user_agent,
    details
):
    """
    属性 35.1: 所有认证事件都被正确记录
    
    **Validates: Requirements 13.1**
    
    对于任意用户认证事件（登录、登出、注册等），系统应该记录：
    - 用户ID
    - 操作类型
    - 成功/失败状态
    - IP地址
    - 用户代理
    - 操作详情
    - 时间戳
    """
    # 记录认证事件
    log_authentication_event(
        db=db_session,
        user_id=user_id,
        action=action,
        success=success,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details
    )
    
    # 验证日志已创建
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == user_id,
        AuditLog.action == action
    ).first()
    
    # 断言：日志必须存在
    assert log is not None, f"认证事件 {action} 未被记录"
    
    # 断言：必须记录用户ID
    assert log.user_id == user_id, "用户ID记录不正确"
    
    # 断言：必须记录操作类型
    assert log.action == action, "操作类型记录不正确"
    
    # 断言：必须记录资源类型为authentication
    assert log.resource_type == "authentication", "资源类型应为authentication"
    
    # 断言：必须记录成功/失败状态
    assert log.details is not None, "详情不应为空"
    assert "success" in log.details, "详情中必须包含success字段"
    assert log.details["success"] == success, "成功状态记录不正确"
    
    # 断言：IP地址正确记录
    assert log.ip_address == ip_address, "IP地址记录不正确"
    
    # 断言：用户代理正确记录
    assert log.user_agent == user_agent, "用户代理记录不正确"
    
    # 断言：必须有时间戳
    assert log.created_at is not None, "必须记录时间戳"
    assert isinstance(log.created_at, datetime), "时间戳类型不正确"
    
    # 断言：时间戳应该是最近的（在过去1分钟内）
    time_diff = datetime.utcnow() - log.created_at
    assert time_diff < timedelta(minutes=1), "时间戳不是最近的"


@given(
    admin_user_id=user_ids,
    action=admin_actions,
    resource_type=resource_types,
    resource_id=user_ids,
    ip_address=ip_addresses,
    user_agent=user_agents,
    details=details_strategy
)
def test_property_admin_operations_are_logged(
    db_session,
    admin_user_id,
    action,
    resource_type,
    resource_id,
    ip_address,
    user_agent,
    details
):
    """
    属性 35.2: 所有管理操作都被正确记录
    
    **Validates: Requirements 13.2**
    
    对于任意管理操作（创建、更新、删除），系统应该记录：
    - 管理员用户ID
    - 操作类型
    - 资源类型
    - 资源ID
    - 操作详情
    - IP地址
    - 用户代理
    - 时间戳
    """
    # 记录管理操作
    log_admin_operation(
        db=db_session,
        user_id=admin_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    # 验证日志已创建
    expected_action = f"{action}_{resource_type}"
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == admin_user_id,
        AuditLog.action == expected_action
    ).first()
    
    # 断言：日志必须存在
    assert log is not None, f"管理操作 {expected_action} 未被记录"
    
    # 断言：必须记录管理员用户ID
    assert log.user_id == admin_user_id, "管理员用户ID记录不正确"
    
    # 断言：必须记录操作类型（格式：action_resource_type）
    assert log.action == expected_action, "操作类型记录不正确"
    
    # 断言：必须记录资源类型
    assert log.resource_type == resource_type, "资源类型记录不正确"
    
    # 断言：必须记录资源ID
    assert log.resource_id == resource_id, "资源ID记录不正确"
    
    # 断言：IP地址正确记录
    assert log.ip_address == ip_address, "IP地址记录不正确"
    
    # 断言：用户代理正确记录
    assert log.user_agent == user_agent, "用户代理记录不正确"
    
    # 断言：必须有时间戳
    assert log.created_at is not None, "必须记录时间戳"
    assert isinstance(log.created_at, datetime), "时间戳类型不正确"



@given(
    admin_user_id=user_ids,
    action=permission_actions,
    target_type=st.sampled_from(["role", "user", "organization"]),
    target_id=user_ids,
    permissions=st.lists(
        st.text(min_size=5, max_size=30, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters=':_')),
        min_size=1,
        max_size=10
    ),
    ip_address=ip_addresses,
    user_agent=user_agents
)
def test_property_permission_changes_are_logged(
    db_session,
    admin_user_id,
    action,
    target_type,
    target_id,
    permissions,
    ip_address,
    user_agent
):
    """
    属性 35.3: 所有权限变更都被正确记录
    
    **Validates: Requirements 13.2**
    
    对于任意权限变更操作，系统应该记录：
    - 操作者用户ID
    - 操作类型（分配/撤销权限）
    - 目标类型（角色/用户/组织）
    - 目标ID
    - 变更的权限列表
    - IP地址
    - 用户代理
    - 时间戳
    """
    # 记录权限变更
    details = {"permissions": permissions}
    log_permission_change(
        db=db_session,
        user_id=admin_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    # 验证日志已创建
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == admin_user_id,
        AuditLog.action == action
    ).first()
    
    # 断言：日志必须存在
    assert log is not None, f"权限变更操作 {action} 未被记录"
    
    # 断言：必须记录操作者用户ID
    assert log.user_id == admin_user_id, "操作者用户ID记录不正确"
    
    # 断言：必须记录操作类型
    assert log.action == action, "操作类型记录不正确"
    
    # 断言：资源类型必须是permission_change
    assert log.resource_type == "permission_change", "资源类型应为permission_change"
    
    # 断言：必须记录目标ID
    assert log.resource_id == target_id, "目标ID记录不正确"
    
    # 断言：详情中必须包含目标类型
    assert log.details is not None, "详情不应为空"
    assert "target_type" in log.details, "详情中必须包含target_type"
    assert log.details["target_type"] == target_type, "目标类型记录不正确"
    
    # 断言：详情中必须包含权限列表
    assert "permissions" in log.details, "详情中必须包含permissions"
    assert log.details["permissions"] == permissions, "权限列表记录不正确"
    
    # 断言：IP地址正确记录
    assert log.ip_address == ip_address, "IP地址记录不正确"
    
    # 断言：用户代理正确记录
    assert log.user_agent == user_agent, "用户代理记录不正确"
    
    # 断言：必须有时间戳
    assert log.created_at is not None, "必须记录时间戳"


@given(
    super_admin_id=user_ids,
    action=super_admin_actions,
    resource_type=st.one_of(resource_types, st.none()),
    resource_id=st.one_of(user_ids, st.none()),
    ip_address=ip_addresses,
    user_agent=user_agents,
    details=details_strategy
)
def test_property_super_admin_operations_are_marked(
    db_session,
    super_admin_id,
    action,
    resource_type,
    resource_id,
    ip_address,
    user_agent,
    details
):
    """
    属性 35.4: 超级管理员的所有操作都被标记
    
    **Validates: Requirements 6.5**
    
    对于任意超级管理员操作，系统应该：
    - 记录所有操作信息
    - 在详情中标记is_super_admin=True
    - 记录完整的操作上下文
    """
    # 记录超级管理员操作
    log_super_admin_operation(
        db=db_session,
        user_id=super_admin_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    # 验证日志已创建
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == super_admin_id,
        AuditLog.action == action
    ).first()
    
    # 断言：日志必须存在
    assert log is not None, f"超级管理员操作 {action} 未被记录"
    
    # 断言：必须记录超级管理员用户ID
    assert log.user_id == super_admin_id, "超级管理员用户ID记录不正确"
    
    # 断言：必须记录操作类型
    assert log.action == action, "操作类型记录不正确"
    
    # 断言：详情中必须标记为超级管理员操作
    assert log.details is not None, "详情不应为空"
    assert "is_super_admin" in log.details, "详情中必须包含is_super_admin标记"
    assert log.details["is_super_admin"] is True, "必须标记为超级管理员操作"
    
    # 断言：资源类型正确记录
    assert log.resource_type == resource_type, "资源类型记录不正确"
    
    # 断言：资源ID正确记录
    assert log.resource_id == resource_id, "资源ID记录不正确"
    
    # 断言：IP地址正确记录
    assert log.ip_address == ip_address, "IP地址记录不正确"
    
    # 断言：用户代理正确记录
    assert log.user_agent == user_agent, "用户代理记录不正确"
    
    # 断言：必须有时间戳
    assert log.created_at is not None, "必须记录时间戳"



@given(
    user_id=user_ids,
    action=st.text(min_size=3, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_')),
    resource_type=st.one_of(resource_types, st.none()),
    resource_id=st.one_of(user_ids, st.none()),
    ip_address=ip_addresses,
    user_agent=user_agents,
    details=details_strategy
)
def test_property_audit_log_completeness(
    db_session,
    user_id,
    action,
    resource_type,
    resource_id,
    ip_address,
    user_agent,
    details
):
    """
    属性 35.5: 审计日志的完整性
    
    **Validates: Requirements 11.9**
    
    对于任意敏感操作，审计日志必须包含所有必要信息：
    - 操作者（user_id）
    - 操作类型（action）
    - 操作时间（created_at）
    - 操作来源（ip_address, user_agent）
    - 操作详情（details）
    
    这些信息对于安全审计和问题追踪至关重要。
    """
    # 创建审计日志
    create_audit_log(
        db=db_session,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    # 验证日志已创建
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == user_id,
        AuditLog.action == action
    ).first()
    
    # 断言：日志必须存在
    assert log is not None, "审计日志未被创建"
    
    # 断言：必须记录操作者
    assert log.user_id == user_id, "操作者记录不正确"
    
    # 断言：必须记录操作类型
    assert log.action == action, "操作类型记录不正确"
    assert len(log.action) > 0, "操作类型不能为空"
    
    # 断言：必须记录操作时间
    assert log.created_at is not None, "必须记录操作时间"
    assert isinstance(log.created_at, datetime), "操作时间类型不正确"
    
    # 断言：操作时间应该是合理的（不能是未来时间）
    assert log.created_at <= datetime.utcnow(), "操作时间不能是未来时间"
    
    # 断言：操作时间应该是最近的（在过去1分钟内）
    time_diff = datetime.utcnow() - log.created_at
    assert time_diff < timedelta(minutes=1), "操作时间应该是最近的"
    
    # 断言：IP地址正确记录
    assert log.ip_address == ip_address, "IP地址记录不正确"
    
    # 断言：用户代理正确记录
    assert log.user_agent == user_agent, "用户代理记录不正确"
    
    # 断言：资源类型正确记录
    assert log.resource_type == resource_type, "资源类型记录不正确"
    
    # 断言：资源ID正确记录
    assert log.resource_id == resource_id, "资源ID记录不正确"
    
    # 断言：详情正确记录（如果提供）
    if details is not None:
        assert log.details == details, "详情记录不正确"


@given(
    user_id=user_ids,
    operations=st.lists(
        st.tuples(
            st.text(min_size=3, max_size=30, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_')),
            resource_types
        ),
        min_size=1,
        max_size=20
    ),
    ip_address=ip_addresses
)
def test_property_audit_log_consistency(
    db_session,
    user_id,
    operations,
    ip_address
):
    """
    属性 35.6: 审计日志的一致性
    
    **Validates: Requirements 11.9, 13.1, 13.2**
    
    对于同一用户的多个操作，审计日志应该：
    - 按时间顺序记录
    - 每个操作都有独立的日志记录
    - 日志记录不会丢失
    - 日志记录不会重复（除非是重复操作）
    """
    # 记录多个操作
    for action, resource_type in operations:
        create_audit_log(
            db=db_session,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            ip_address=ip_address
        )
    
    # 查询该用户的所有日志
    logs = db_session.query(AuditLog).filter(
        AuditLog.user_id == user_id
    ).order_by(AuditLog.created_at).all()
    
    # 断言：日志数量应该等于操作数量
    assert len(logs) == len(operations), f"日志数量不匹配：期望{len(operations)}，实际{len(logs)}"
    
    # 断言：每个操作都被记录
    logged_operations = [(log.action, log.resource_type) for log in logs]
    for operation in operations:
        assert operation in logged_operations, f"操作 {operation} 未被记录"
    
    # 断言：日志按时间顺序排列
    for i in range(len(logs) - 1):
        assert logs[i].created_at <= logs[i + 1].created_at, "日志未按时间顺序排列"
    
    # 断言：所有日志都有相同的用户ID
    for log in logs:
        assert log.user_id == user_id, "日志的用户ID不一致"
    
    # 断言：所有日志都有相同的IP地址（如果提供）
    if ip_address is not None:
        for log in logs:
            assert log.ip_address == ip_address, "日志的IP地址不一致"



@given(
    user_id=st.one_of(user_ids, st.none()),
    action=st.text(min_size=3, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_')),
    ip_address=ip_addresses
)
def test_property_anonymous_operations_are_logged(
    db_session,
    user_id,
    action,
    ip_address
):
    """
    属性 35.7: 匿名操作也被记录
    
    **Validates: Requirements 11.9, 13.1**
    
    即使是匿名操作（没有用户ID），系统也应该记录审计日志，
    以便追踪所有系统活动，包括：
    - 失败的登录尝试
    - 未授权的访问尝试
    - 公开API的调用
    """
    # 创建审计日志（可能没有用户ID）
    create_audit_log(
        db=db_session,
        user_id=user_id,
        action=action,
        ip_address=ip_address
    )
    
    # 验证日志已创建
    if user_id is not None:
        log = db_session.query(AuditLog).filter(
            AuditLog.user_id == user_id,
            AuditLog.action == action
        ).first()
    else:
        log = db_session.query(AuditLog).filter(
            AuditLog.action == action,
            AuditLog.user_id.is_(None)
        ).first()
    
    # 断言：日志必须存在
    assert log is not None, "匿名操作未被记录"
    
    # 断言：用户ID正确记录（可能为None）
    assert log.user_id == user_id, "用户ID记录不正确"
    
    # 断言：操作类型正确记录
    assert log.action == action, "操作类型记录不正确"
    
    # 断言：IP地址正确记录（对于匿名操作尤其重要）
    assert log.ip_address == ip_address, "IP地址记录不正确"
    
    # 断言：必须有时间戳
    assert log.created_at is not None, "必须记录时间戳"


@given(
    user_id=user_ids,
    action=st.text(min_size=3, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_')),
    details=st.dictionaries(
        st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll'))),
        st.one_of(
            st.text(max_size=100),
            st.integers(),
            st.booleans(),
            st.none(),
            st.lists(st.text(max_size=50), max_size=5)
        ),
        min_size=1,
        max_size=10
    )
)
def test_property_audit_log_details_integrity(
    db_session,
    user_id,
    action,
    details
):
    """
    属性 35.8: 审计日志详情的完整性
    
    **Validates: Requirements 11.9**
    
    审计日志的详情字段应该：
    - 能够存储复杂的JSON数据
    - 保持数据的完整性（不丢失、不损坏）
    - 支持各种数据类型（字符串、数字、布尔、数组、对象）
    """
    # 创建包含详情的审计日志
    create_audit_log(
        db=db_session,
        user_id=user_id,
        action=action,
        details=details
    )
    
    # 验证日志已创建
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == user_id,
        AuditLog.action == action
    ).first()
    
    # 断言：日志必须存在
    assert log is not None, "审计日志未被创建"
    
    # 断言：详情必须完整保存
    assert log.details is not None, "详情不应为空"
    assert log.details == details, "详情内容不匹配"
    
    # 断言：详情中的所有键都被保存
    for key in details.keys():
        assert key in log.details, f"详情中的键 {key} 丢失"
    
    # 断言：详情中的所有值都被正确保存
    for key, value in details.items():
        assert log.details[key] == value, f"详情中的值 {key}={value} 不匹配"


@given(
    operations=st.lists(
        st.tuples(
            user_ids,
            st.text(min_size=3, max_size=30, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_')),
            ip_addresses
        ),
        min_size=5,
        max_size=50
    )
)
def test_property_audit_log_scalability(
    db_session,
    operations
):
    """
    属性 35.9: 审计日志的可扩展性
    
    **Validates: Requirements 9.8, 11.9**
    
    审计日志系统应该能够处理大量的日志记录：
    - 支持批量记录
    - 不影响系统性能
    - 保持数据一致性
    """
    # 记录大量操作
    for user_id, action, ip_address in operations:
        create_audit_log(
            db=db_session,
            user_id=user_id,
            action=action,
            ip_address=ip_address
        )
    
    # 验证所有日志都被创建
    total_logs = db_session.query(AuditLog).count()
    
    # 断言：日志数量应该等于操作数量
    assert total_logs >= len(operations), f"部分日志丢失：期望至少{len(operations)}，实际{total_logs}"
    
    # 验证每个操作都被记录
    for user_id, action, ip_address in operations:
        log = db_session.query(AuditLog).filter(
            AuditLog.user_id == user_id,
            AuditLog.action == action,
            AuditLog.ip_address == ip_address
        ).first()
        
        assert log is not None, f"操作 {action} (用户 {user_id}) 未被记录"


@given(
    user_id=user_ids,
    success_action=authentication_actions,
    failure_action=authentication_actions,
    ip_address=ip_addresses
)
def test_property_authentication_success_and_failure_logged(
    db_session,
    user_id,
    success_action,
    failure_action,
    ip_address
):
    """
    属性 35.10: 认证成功和失败都被记录
    
    **Validates: Requirements 13.1**
    
    系统应该记录所有认证事件，无论成功还是失败：
    - 成功的认证事件
    - 失败的认证事件
    - 两者都包含完整的上下文信息
    """
    # 记录成功的认证事件
    log_authentication_event(
        db=db_session,
        user_id=user_id,
        action=success_action,
        success=True,
        ip_address=ip_address,
        details={"method": "password"}
    )
    
    # 记录失败的认证事件
    log_authentication_event(
        db=db_session,
        user_id=user_id,
        action=failure_action,
        success=False,
        ip_address=ip_address,
        details={"reason": "invalid_credentials", "attempts": 3}
    )
    
    # 验证成功事件被记录
    success_log = db_session.query(AuditLog).filter(
        AuditLog.user_id == user_id,
        AuditLog.action == success_action
    ).first()
    
    assert success_log is not None, "成功的认证事件未被记录"
    assert success_log.details["success"] is True, "成功状态记录不正确"
    
    # 验证失败事件被记录
    failure_log = db_session.query(AuditLog).filter(
        AuditLog.user_id == user_id,
        AuditLog.action == failure_action
    ).first()
    
    assert failure_log is not None, "失败的认证事件未被记录"
    assert failure_log.details["success"] is False, "失败状态记录不正确"
    
    # 断言：两个事件都有时间戳
    assert success_log.created_at is not None, "成功事件必须有时间戳"
    assert failure_log.created_at is not None, "失败事件必须有时间戳"


# ==================== 边界情况和健壮性测试 ====================

@given(
    user_id=user_ids,
    action=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'P', 'S'))),
)
def test_property_audit_log_handles_special_characters(
    db_session,
    user_id,
    action
):
    """
    属性 35.11: 审计日志处理特殊字符
    
    审计日志应该能够正确处理包含特殊字符的操作类型。
    """
    # 过滤掉可能导致问题的字符
    assume(len(action.strip()) > 0)
    
    # 创建审计日志
    create_audit_log(
        db=db_session,
        user_id=user_id,
        action=action
    )
    
    # 验证日志已创建
    log = db_session.query(AuditLog).filter(
        AuditLog.user_id == user_id,
        AuditLog.action == action
    ).first()
    
    # 断言：日志必须存在
    assert log is not None, "包含特殊字符的操作未被记录"
    
    # 断言：操作类型完整保存
    assert log.action == action, "操作类型记录不正确"


# ==================== 测试总结 ====================

"""
属性测试总结：

本测试套件验证了审计日志系统的以下属性：

1. ✅ 所有认证事件都被正确记录（需求 13.1）
2. ✅ 所有管理操作都被正确记录（需求 13.2）
3. ✅ 所有权限变更都被正确记录（需求 13.2）
4. ✅ 超级管理员的所有操作都被标记（需求 6.5）
5. ✅ 审计日志的完整性（需求 11.9）
6. ✅ 审计日志的一致性（需求 11.9, 13.1, 13.2）
7. ✅ 匿名操作也被记录（需求 11.9, 13.1）
8. ✅ 审计日志详情的完整性（需求 11.9）
9. ✅ 审计日志的可扩展性（需求 9.8, 11.9）
10. ✅ 认证成功和失败都被记录（需求 13.1）
11. ✅ 审计日志处理特殊字符

这些属性测试通过随机生成大量测试用例，验证了审计日志系统在各种情况下的正确性和健壮性。
每个测试运行100次迭代，覆盖了广泛的输入空间。
"""
