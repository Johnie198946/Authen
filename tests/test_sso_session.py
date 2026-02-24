"""
测试SSO会话管理功能

需求：2.1, 2.2 - SSO会话创建、查询、验证和更新
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from shared.models.user import Base, User, SSOSession
from shared.utils.crypto import hash_password
from shared.utils.sso_session import (
    create_sso_session,
    get_sso_session,
    validate_sso_session,
    update_session_activity,
    delete_sso_session,
    delete_user_sso_sessions,
    get_user_active_sessions
)


# 测试数据库配置
TEST_DATABASE_URL = "sqlite:///./test_sso.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前设置数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    """数据库会话fixture"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_user(db: Session):
    """创建测试用户"""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash=hash_password("TestPass123!"),
        status="active"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_create_sso_session(db: Session, test_user: User):
    """
    测试创建SSO会话
    
    需求：2.1 - 用户在任一应用登录成功时创建全局会话
    """
    # 创建SSO会话
    session = create_sso_session(str(test_user.id), db)
    
    # 验证会话创建成功
    assert session is not None
    assert session.user_id == test_user.id
    assert session.session_token is not None
    assert len(session.session_token) > 0
    assert session.expires_at > datetime.utcnow()
    assert session.last_activity_at is not None
    
    # 验证会话可以从数据库查询到
    db_session = db.query(SSOSession).filter(
        SSOSession.session_token == session.session_token
    ).first()
    assert db_session is not None
    assert db_session.user_id == test_user.id


def test_get_sso_session(db: Session, test_user: User):
    """
    测试查询SSO会话
    
    需求：2.2 - 其他应用可以查询SSO会话
    """
    # 创建会话
    session = create_sso_session(str(test_user.id), db)
    
    # 查询会话
    retrieved_session = get_sso_session(session.session_token, db)
    
    # 验证查询结果
    assert retrieved_session is not None
    assert retrieved_session.id == session.id
    assert retrieved_session.user_id == test_user.id
    assert retrieved_session.session_token == session.session_token


def test_get_nonexistent_session(db: Session):
    """测试查询不存在的会话"""
    session = get_sso_session("nonexistent_token", db)
    assert session is None


def test_get_expired_session(db: Session, test_user: User):
    """测试查询过期的会话"""
    # 创建会话
    session = create_sso_session(str(test_user.id), db)
    
    # 手动设置会话为过期
    session.expires_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()
    
    # 查询过期会话应该返回None并删除会话
    retrieved_session = get_sso_session(session.session_token, db)
    assert retrieved_session is None
    
    # 验证会话已被删除
    db_session = db.query(SSOSession).filter(
        SSOSession.session_token == session.session_token
    ).first()
    assert db_session is None


def test_validate_sso_session(db: Session, test_user: User):
    """
    测试验证SSO会话
    
    需求：2.2 - 验证SSO会话的有效性
    """
    # 创建会话
    session = create_sso_session(str(test_user.id), db)
    
    # 验证会话
    is_valid, error_msg, validated_session = validate_sso_session(
        session.session_token, db
    )
    
    # 验证结果
    assert is_valid is True
    assert error_msg == ""
    assert validated_session is not None
    assert validated_session.id == session.id


def test_validate_empty_token(db: Session):
    """测试验证空令牌"""
    is_valid, error_msg, session = validate_sso_session("", db)
    
    assert is_valid is False
    assert "不能为空" in error_msg
    assert session is None


def test_validate_nonexistent_session(db: Session):
    """测试验证不存在的会话"""
    is_valid, error_msg, session = validate_sso_session("nonexistent_token", db)
    
    assert is_valid is False
    assert "不存在或已过期" in error_msg
    assert session is None


def test_update_session_activity(db: Session, test_user: User):
    """
    测试更新会话活动时间
    
    需求：2.1, 2.2 - 更新会话的最后活动时间
    """
    # 创建会话
    session = create_sso_session(str(test_user.id), db)
    original_activity_time = session.last_activity_at
    
    # 等待一小段时间
    import time
    time.sleep(0.1)
    
    # 更新活动时间
    success = update_session_activity(session.session_token, db)
    
    # 验证更新成功
    assert success is True
    
    # 重新查询会话
    db.refresh(session)
    assert session.last_activity_at > original_activity_time


def test_update_nonexistent_session_activity(db: Session):
    """测试更新不存在的会话活动时间"""
    success = update_session_activity("nonexistent_token", db)
    assert success is False


def test_update_expired_session_activity(db: Session, test_user: User):
    """测试更新过期会话的活动时间"""
    # 创建会话
    session = create_sso_session(str(test_user.id), db)
    
    # 手动设置会话为过期
    session.expires_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()
    
    # 尝试更新过期会话应该失败
    success = update_session_activity(session.session_token, db)
    assert success is False
    
    # 验证会话已被删除
    db_session = db.query(SSOSession).filter(
        SSOSession.session_token == session.session_token
    ).first()
    assert db_session is None


def test_delete_sso_session(db: Session, test_user: User):
    """
    测试删除SSO会话
    
    需求：2.3 - 用户登出时终止全局会话
    """
    # 创建会话
    session = create_sso_session(str(test_user.id), db)
    
    # 删除会话
    success = delete_sso_session(session.session_token, db)
    
    # 验证删除成功
    assert success is True
    
    # 验证会话已被删除
    db_session = db.query(SSOSession).filter(
        SSOSession.session_token == session.session_token
    ).first()
    assert db_session is None


def test_delete_nonexistent_session(db: Session):
    """测试删除不存在的会话"""
    success = delete_sso_session("nonexistent_token", db)
    assert success is False


def test_delete_user_sso_sessions(db: Session, test_user: User):
    """
    测试删除用户的所有SSO会话
    
    需求：2.3 - 用户在任一应用登出时终止所有应用的会话
    """
    # 创建多个会话
    session1 = create_sso_session(str(test_user.id), db)
    session2 = create_sso_session(str(test_user.id), db)
    session3 = create_sso_session(str(test_user.id), db)
    
    # 删除用户的所有会话
    count = delete_user_sso_sessions(str(test_user.id), db)
    
    # 验证删除数量
    assert count == 3
    
    # 验证所有会话都已被删除
    remaining_sessions = db.query(SSOSession).filter(
        SSOSession.user_id == test_user.id
    ).all()
    assert len(remaining_sessions) == 0


def test_get_user_active_sessions(db: Session, test_user: User):
    """测试获取用户的活跃会话"""
    # 创建多个会话
    session1 = create_sso_session(str(test_user.id), db)
    session2 = create_sso_session(str(test_user.id), db)
    
    # 创建一个过期会话
    expired_session = create_sso_session(str(test_user.id), db)
    expired_session.expires_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()
    
    # 获取活跃会话
    active_sessions = get_user_active_sessions(str(test_user.id), db)
    
    # 验证只返回未过期的会话
    assert len(active_sessions) == 2
    session_ids = [s.id for s in active_sessions]
    assert session1.id in session_ids
    assert session2.id in session_ids
    assert expired_session.id not in session_ids


def test_multiple_users_sessions(db: Session):
    """测试多个用户的会话隔离"""
    # 创建两个用户
    user1 = User(
        username="user1",
        email="user1@example.com",
        password_hash=hash_password("Pass123!"),
        status="active"
    )
    user2 = User(
        username="user2",
        email="user2@example.com",
        password_hash=hash_password("Pass123!"),
        status="active"
    )
    db.add(user1)
    db.add(user2)
    db.commit()
    db.refresh(user1)
    db.refresh(user2)
    
    # 为每个用户创建会话
    session1 = create_sso_session(str(user1.id), db)
    session2 = create_sso_session(str(user2.id), db)
    
    # 验证会话属于正确的用户
    assert session1.user_id == user1.id
    assert session2.user_id == user2.id
    
    # 删除user1的会话不应影响user2
    delete_user_sso_sessions(str(user1.id), db)
    
    # 验证user2的会话仍然存在
    user2_sessions = get_user_active_sessions(str(user2.id), db)
    assert len(user2_sessions) == 1
    assert user2_sessions[0].id == session2.id
