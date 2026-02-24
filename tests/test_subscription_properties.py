"""
订阅服务属性测试

Feature: unified-auth-platform, Properties 12-16: 订阅管理

验证需求：3.1, 3.2, 3.3, 3.5, 3.6
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database import Base, get_db
from shared.models.subscription import SubscriptionPlan, UserSubscription
from shared.models.user import User
from services.subscription.main import app
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

# 测试数据库
TEST_DATABASE_URL = "sqlite:///./test_subscription_properties.db"
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

# Hypothesis策略
plan_names = st.text(
    alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs')),
    min_size=3,
    max_size=50
)

plan_durations = st.integers(min_value=1, max_value=365)  # 1天到1年
plan_prices = st.floats(min_value=0.01, max_value=9999.99, allow_nan=False, allow_infinity=False)

@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前重置数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


class TestProperty12SubscriptionPurchaseIntegrity:
    """
    属性 12：订阅购买完整性
    
    对于任意用户和订阅计划，当用户购买订阅时，
    系统应该正确记录订阅信息（开始日期、结束日期、计划ID），
    并且用户的订阅状态应该变为active。
    
    **验证需求：3.1**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        duration_days=plan_durations,
        price=plan_prices,
        auto_renew=st.booleans()
    )
    def test_subscription_purchase_creates_valid_subscription(self, plan_name, duration_days, price, auto_renew):
        """
        属性测试：订阅购买创建有效的订阅记录
        
        给定：一个用户和一个订阅计划
        当：用户购买订阅
        则：应该创建订阅记录，包含正确的开始日期、结束日期、状态和计划ID
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=duration_days,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            plan_id = str(plan.id)
            
            # 记录购买前的时间
            before_purchase = datetime.utcnow()
            
            # 购买订阅
            response = client.post(
                f"/api/v1/users/{user_id}/subscription",
                json={"plan_id": plan_id, "auto_renew": auto_renew}
            )
            
            # 记录购买后的时间
            after_purchase = datetime.utcnow()
            
            # 验证响应
            assert response.status_code == 200
            data = response.json()
            
            # 验证订阅记录的完整性
            assert data["user_id"] == user_id
            assert data["plan_id"] == plan_id
            assert data["status"] == "active"
            assert data["auto_renew"] == auto_renew
            
            # 验证开始日期在合理范围内
            start_date = datetime.fromisoformat(data["start_date"].replace('Z', '+00:00'))
            assert before_purchase <= start_date <= after_purchase
            
            # 验证结束日期 = 开始日期 + duration_days
            end_date = datetime.fromisoformat(data["end_date"].replace('Z', '+00:00'))
            expected_end_date = start_date + timedelta(days=duration_days)
            
            # 允许1秒的误差
            time_diff = abs((end_date - expected_end_date).total_seconds())
            assert time_diff < 1, f"End date mismatch: {end_date} vs {expected_end_date}"
            
            # 验证订阅ID存在
            assert "id" in data
            assert data["id"] is not None
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        duration_days=plan_durations,
        price=plan_prices
    )
    def test_user_can_query_active_subscription_after_purchase(self, plan_name, duration_days, price):
        """
        属性测试：购买后可以查询到活跃订阅
        
        给定：用户购买了订阅
        当：查询用户订阅状态
        则：应该返回活跃的订阅信息
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=duration_days,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            plan_id = str(plan.id)
            
            # 购买订阅
            purchase_response = client.post(
                f"/api/v1/users/{user_id}/subscription",
                json={"plan_id": plan_id, "auto_renew": True}
            )
            assert purchase_response.status_code == 200
            subscription_id = purchase_response.json()["id"]
            
            # 查询订阅
            query_response = client.get(f"/api/v1/users/{user_id}/subscription")
            
            # 验证
            assert query_response.status_code == 200
            data = query_response.json()
            
            # 应该返回刚购买的订阅
            assert data["id"] == subscription_id
            assert data["user_id"] == user_id
            assert data["plan_id"] == plan_id
            assert data["status"] == "active"
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        duration_days=plan_durations,
        price=plan_prices
    )
    def test_cannot_purchase_duplicate_active_subscription(self, plan_name, duration_days, price):
        """
        属性测试：不能购买重复的活跃订阅
        
        给定：用户已有活跃订阅
        当：尝试再次购买订阅
        则：应该返回错误
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=duration_days,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            plan_id = str(plan.id)
            
            # 第一次购买订阅
            response1 = client.post(
                f"/api/v1/users/{user_id}/subscription",
                json={"plan_id": plan_id, "auto_renew": True}
            )
            assert response1.status_code == 200
            
            # 第二次购买订阅（应该失败）
            response2 = client.post(
                f"/api/v1/users/{user_id}/subscription",
                json={"plan_id": plan_id, "auto_renew": True}
            )
            
            # 验证：应该返回冲突错误
            assert response2.status_code == 409
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        duration_days=plan_durations,
        price=plan_prices
    )
    def test_purchase_with_nonexistent_plan_fails(self, plan_name, duration_days, price):
        """
        属性测试：使用不存在的计划购买失败
        
        给定：一个不存在的订阅计划ID
        当：尝试购买该计划
        则：应该返回404错误
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 使用不存在的计划ID
            fake_plan_id = str(uuid.uuid4())
            
            # 尝试购买
            response = client.post(
                f"/api/v1/users/{user_id}/subscription",
                json={"plan_id": fake_plan_id, "auto_renew": True}
            )
            
            # 验证：应该返回404错误
            assert response.status_code == 404
        finally:
            db_session.close()


class TestProperty15SubscriptionStatusQuery:
    """
    属性 15：订阅状态查询
    
    对于任意用户，查询其订阅状态时，
    系统应该返回正确的订阅级别、到期时间和自动续费状态。
    
    **验证需求：3.5**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        duration_days=plan_durations,
        price=plan_prices,
        auto_renew=st.booleans()
    )
    def test_query_returns_correct_subscription_details(self, plan_name, duration_days, price, auto_renew):
        """
        属性测试：查询返回正确的订阅详情
        
        给定：用户有活跃订阅
        当：查询订阅状态
        则：应该返回正确的计划ID、到期时间和自动续费状态
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=duration_days,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            plan_id = str(plan.id)
            
            # 购买订阅
            purchase_response = client.post(
                f"/api/v1/users/{user_id}/subscription",
                json={"plan_id": plan_id, "auto_renew": auto_renew}
            )
            assert purchase_response.status_code == 200
            purchase_data = purchase_response.json()
            
            # 查询订阅状态
            query_response = client.get(f"/api/v1/users/{user_id}/subscription")
            
            # 验证
            assert query_response.status_code == 200
            query_data = query_response.json()
            
            # 验证订阅详情正确
            assert query_data["plan_id"] == plan_id
            assert query_data["auto_renew"] == auto_renew
            assert query_data["status"] == "active"
            
            # 验证到期时间一致
            assert query_data["end_date"] == purchase_data["end_date"]
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(plan_name=plan_names)
    def test_query_without_subscription_returns_null(self, plan_name):
        """
        属性测试：没有订阅的用户查询返回null
        
        给定：用户没有订阅
        当：查询订阅状态
        则：应该返回null或空订阅
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户（不购买订阅）
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 查询订阅状态
            response = client.get(f"/api/v1/users/{user_id}/subscription")
            
            # 验证
            assert response.status_code == 200
            data = response.json()
            
            # 应该返回空订阅
            assert data.get("subscription") is None or data.get("id") is None
        finally:
            db_session.close()


class TestProperty14SubscriptionCancellation:
    """
    属性 14：订阅取消处理
    
    对于任意活跃订阅，当用户取消订阅时，
    系统应该将auto_renew标记为false，
    且订阅应该在当前周期结束后自动过期。
    
    **验证需求：3.3**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        duration_days=plan_durations,
        price=plan_prices
    )
    def test_cancellation_sets_auto_renew_to_false(self, plan_name, duration_days, price):
        """
        属性测试：取消订阅将auto_renew设为false
        
        给定：用户有活跃订阅且auto_renew为true
        当：取消订阅
        则：auto_renew应该变为false，但订阅仍然active
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=duration_days,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            plan_id = str(plan.id)
            
            # 购买订阅（auto_renew=true）
            purchase_response = client.post(
                f"/api/v1/users/{user_id}/subscription",
                json={"plan_id": plan_id, "auto_renew": True}
            )
            assert purchase_response.status_code == 200
            
            # 验证初始状态
            query_response1 = client.get(f"/api/v1/users/{user_id}/subscription")
            assert query_response1.status_code == 200
            data1 = query_response1.json()
            assert data1["auto_renew"] is True
            assert data1["status"] == "active"
            
            # 取消订阅
            cancel_response = client.delete(f"/api/v1/users/{user_id}/subscription")
            
            # 验证取消成功
            assert cancel_response.status_code == 200
            
            # 查询订阅状态
            query_response2 = client.get(f"/api/v1/users/{user_id}/subscription")
            assert query_response2.status_code == 200
            data2 = query_response2.json()
            
            # 验证auto_renew变为false，但订阅仍然active
            assert data2["auto_renew"] is False
            assert data2["status"] == "active"
            
            # 验证到期时间没有改变
            assert data2["end_date"] == data1["end_date"]
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(plan_name=plan_names)
    def test_cannot_cancel_nonexistent_subscription(self, plan_name):
        """
        属性测试：不能取消不存在的订阅
        
        给定：用户没有活跃订阅
        当：尝试取消订阅
        则：应该返回404错误
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户（不购买订阅）
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 尝试取消订阅
            response = client.delete(f"/api/v1/users/{user_id}/subscription")
            
            # 验证：应该返回404错误
            assert response.status_code == 404
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        duration_days=plan_durations,
        price=plan_prices
    )
    def test_cancellation_is_idempotent(self, plan_name, duration_days, price):
        """
        属性测试：取消订阅是幂等的
        
        给定：用户已取消订阅
        当：再次取消订阅
        则：应该成功（或返回合理的响应）
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=duration_days,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            plan_id = str(plan.id)
            
            # 购买订阅
            purchase_response = client.post(
                f"/api/v1/users/{user_id}/subscription",
                json={"plan_id": plan_id, "auto_renew": True}
            )
            assert purchase_response.status_code == 200
            
            # 第一次取消
            cancel_response1 = client.delete(f"/api/v1/users/{user_id}/subscription")
            assert cancel_response1.status_code == 200
            
            # 第二次取消
            cancel_response2 = client.delete(f"/api/v1/users/{user_id}/subscription")
            assert cancel_response2.status_code == 200
            
            # 验证订阅状态一致
            query_response = client.get(f"/api/v1/users/{user_id}/subscription")
            assert query_response.status_code == 200
            data = query_response.json()
            assert data["auto_renew"] is False
            assert data["status"] == "active"
        finally:
            db_session.close()


class TestProperty13SubscriptionExpirationDowngrade:
    """
    属性 13：订阅到期权限降级
    
    对于任意已到期的订阅，系统应该自动将订阅状态更新为expired，
    且用户不应该再拥有该订阅计划提供的权益。
    
    **验证需求：3.2**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        price=plan_prices
    )
    def test_expired_subscription_status_updated(self, plan_name, price):
        """
        属性测试：到期订阅状态自动更新
        
        给定：用户有一个已到期的订阅
        当：运行到期处理任务
        则：订阅状态应该变为expired
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=1,  # 1天订阅
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            
            # 创建一个已到期的订阅（手动设置过去的日期）
            past_start = datetime.utcnow() - timedelta(days=2)
            past_end = datetime.utcnow() - timedelta(hours=1)  # 1小时前到期
            
            subscription = UserSubscription(
                id=uuid.uuid4(),
                user_id=user.id,
                plan_id=plan.id,
                status='active',
                start_date=past_start,
                end_date=past_end,
                auto_renew=False
            )
            db_session.add(subscription)
            db_session.commit()
            db_session.refresh(subscription)
            
            # 验证初始状态为active
            assert subscription.status == 'active'
            
            # 触发到期处理
            response = client.post("/api/v1/admin/subscriptions/process-expired")
            
            # 验证处理成功
            assert response.status_code == 200
            data = response.json()
            assert data["processed"] >= 1
            
            # 刷新订阅对象
            db_session.refresh(subscription)
            
            # 验证订阅状态已更新为expired
            assert subscription.status == 'expired'
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        price=plan_prices,
        num_expired=st.integers(min_value=1, max_value=5)
    )
    def test_multiple_expired_subscriptions_processed(self, plan_name, price, num_expired):
        """
        属性测试：批量处理多个到期订阅
        
        给定：多个用户有到期的订阅
        当：运行到期处理任务
        则：所有到期订阅的状态都应该变为expired
        """
        db_session = TestingSessionLocal()
        try:
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=1,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            
            # 创建多个用户和到期订阅
            user_ids = []
            for i in range(num_expired):
                user = User(
                    id=uuid.uuid4(),
                    username=f"testuser_{uuid.uuid4().hex[:8]}",
                    email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                    password_hash="hashed_password",
                    status="active"
                )
                db_session.add(user)
                db_session.commit()
                db_session.refresh(user)
                user_ids.append(str(user.id))
                
                # 创建已到期的订阅
                past_start = datetime.utcnow() - timedelta(days=2)
                past_end = datetime.utcnow() - timedelta(hours=1)
                
                subscription = UserSubscription(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    plan_id=plan.id,
                    status='active',
                    start_date=past_start,
                    end_date=past_end,
                    auto_renew=False
                )
                db_session.add(subscription)
            
            db_session.commit()
            
            # 触发到期处理
            response = client.post("/api/v1/admin/subscriptions/process-expired")
            
            # 验证处理成功
            assert response.status_code == 200
            data = response.json()
            assert data["processed"] >= num_expired
            
            # 验证所有用户的订阅都已过期（通过查询API）
            for user_id in user_ids:
                query_response = client.get(f"/api/v1/users/{user_id}/subscription")
                assert query_response.status_code == 200
                query_data = query_response.json()
                # 已过期的订阅不应该在查询中返回（因为只查询active订阅）
                assert query_data.get("subscription") is None or query_data.get("id") is None
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        price=plan_prices
    )
    def test_active_subscriptions_not_affected(self, plan_name, price):
        """
        属性测试：未到期订阅不受影响
        
        给定：用户有一个未到期的活跃订阅
        当：运行到期处理任务
        则：订阅状态应该保持active
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=30,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            
            # 创建未到期的订阅
            start_date = datetime.utcnow()
            end_date = start_date + timedelta(days=30)  # 30天后到期
            
            subscription = UserSubscription(
                id=uuid.uuid4(),
                user_id=user.id,
                plan_id=plan.id,
                status='active',
                start_date=start_date,
                end_date=end_date,
                auto_renew=True
            )
            db_session.add(subscription)
            db_session.commit()
            db_session.refresh(subscription)
            
            # 验证初始状态为active
            assert subscription.status == 'active'
            
            # 触发到期处理
            response = client.post("/api/v1/admin/subscriptions/process-expired")
            
            # 验证处理成功
            assert response.status_code == 200
            
            # 刷新订阅对象
            db_session.refresh(subscription)
            
            # 验证订阅状态仍然是active
            assert subscription.status == 'active'
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        price=plan_prices
    )
    def test_expired_subscription_not_returned_in_query(self, plan_name, price):
        """
        属性测试：到期订阅不在查询中返回
        
        给定：用户有一个已到期并处理过的订阅
        当：查询用户订阅
        则：应该返回空（因为只查询active订阅）
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=1,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            
            # 创建已到期的订阅
            past_start = datetime.utcnow() - timedelta(days=2)
            past_end = datetime.utcnow() - timedelta(hours=1)
            
            subscription = UserSubscription(
                id=uuid.uuid4(),
                user_id=user.id,
                plan_id=plan.id,
                status='active',
                start_date=past_start,
                end_date=past_end,
                auto_renew=False
            )
            db_session.add(subscription)
            db_session.commit()
            
            # 触发到期处理
            process_response = client.post("/api/v1/admin/subscriptions/process-expired")
            assert process_response.status_code == 200
            
            # 查询用户订阅
            query_response = client.get(f"/api/v1/users/{user_id}/subscription")
            
            # 验证返回空订阅
            assert query_response.status_code == 200
            data = query_response.json()
            assert data.get("subscription") is None or data.get("id") is None
        finally:
            db_session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])



class TestProperty16SubscriptionExpirationReminder:
    """
    属性 16：订阅到期提醒
    
    对于任意将在7天内到期的订阅，系统应该发送提醒通知给用户。
    
    **验证需求：3.6**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        price=plan_prices,
        days_until_expiry=st.integers(min_value=1, max_value=7)
    )
    def test_reminder_sent_for_expiring_subscriptions(self, plan_name, price, days_until_expiry):
        """
        属性测试：为即将到期的订阅发送提醒
        
        给定：用户有一个将在7天内到期的订阅
        当：运行提醒发送任务
        则：应该为该订阅发送提醒
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=30,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            
            # 创建一个将在指定天数后到期的订阅
            start_date = datetime.utcnow() - timedelta(days=30 - days_until_expiry)
            end_date = datetime.utcnow() + timedelta(days=days_until_expiry)
            
            subscription = UserSubscription(
                id=uuid.uuid4(),
                user_id=user.id,
                plan_id=plan.id,
                status='active',
                start_date=start_date,
                end_date=end_date,
                auto_renew=True
            )
            db_session.add(subscription)
            db_session.commit()
            
            # 触发提醒发送
            response = client.post("/api/v1/admin/subscriptions/send-reminders")
            
            # 验证提醒发送成功
            assert response.status_code == 200
            data = response.json()
            assert data["reminded"] >= 1
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        price=plan_prices,
        days_until_expiry=st.integers(min_value=8, max_value=30)
    )
    def test_no_reminder_for_far_future_expiry(self, plan_name, price, days_until_expiry):
        """
        属性测试：不为远期到期的订阅发送提醒
        
        给定：用户有一个将在7天后才到期的订阅
        当：运行提醒发送任务
        则：不应该为该订阅发送提醒
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=60,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            
            # 创建一个将在指定天数后到期的订阅（超过7天）
            start_date = datetime.utcnow()
            end_date = datetime.utcnow() + timedelta(days=days_until_expiry)
            
            subscription = UserSubscription(
                id=uuid.uuid4(),
                user_id=user.id,
                plan_id=plan.id,
                status='active',
                start_date=start_date,
                end_date=end_date,
                auto_renew=True
            )
            db_session.add(subscription)
            db_session.commit()
            
            # 触发提醒发送
            response = client.post("/api/v1/admin/subscriptions/send-reminders")
            
            # 验证提醒发送成功（但不应该包含这个订阅）
            assert response.status_code == 200
            data = response.json()
            # 这个订阅不应该被提醒（reminded可能是0，因为没有其他订阅）
            assert data["reminded"] == 0
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        price=plan_prices,
        num_expiring=st.integers(min_value=1, max_value=5)
    )
    def test_multiple_reminders_sent(self, plan_name, price, num_expiring):
        """
        属性测试：批量发送多个提醒
        
        给定：多个用户有即将到期的订阅
        当：运行提醒发送任务
        则：应该为所有即将到期的订阅发送提醒
        """
        db_session = TestingSessionLocal()
        try:
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=30,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            
            # 创建多个用户和即将到期的订阅
            for i in range(num_expiring):
                user = User(
                    id=uuid.uuid4(),
                    username=f"testuser_{uuid.uuid4().hex[:8]}",
                    email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                    password_hash="hashed_password",
                    status="active"
                )
                db_session.add(user)
                db_session.commit()
                db_session.refresh(user)
                
                # 创建将在3天后到期的订阅
                start_date = datetime.utcnow() - timedelta(days=27)
                end_date = datetime.utcnow() + timedelta(days=3)
                
                subscription = UserSubscription(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    plan_id=plan.id,
                    status='active',
                    start_date=start_date,
                    end_date=end_date,
                    auto_renew=True
                )
                db_session.add(subscription)
            
            db_session.commit()
            
            # 触发提醒发送
            response = client.post("/api/v1/admin/subscriptions/send-reminders")
            
            # 验证提醒发送成功
            assert response.status_code == 200
            data = response.json()
            assert data["reminded"] >= num_expiring
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        plan_name=plan_names,
        price=plan_prices
    )
    def test_no_reminder_for_expired_subscriptions(self, plan_name, price):
        """
        属性测试：不为已过期的订阅发送提醒
        
        给定：用户有一个已过期的订阅
        当：运行提醒发送任务
        则：不应该为该订阅发送提醒
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            
            # 创建订阅计划
            plan = SubscriptionPlan(
                id=uuid.uuid4(),
                name=f"{plan_name}_{uuid.uuid4().hex[:8]}",
                description="Test plan",
                duration_days=30,
                price=Decimal(str(round(price, 2))),
                is_active=True
            )
            db_session.add(plan)
            db_session.commit()
            db_session.refresh(plan)
            
            # 创建一个已过期的订阅
            past_start = datetime.utcnow() - timedelta(days=32)
            past_end = datetime.utcnow() - timedelta(days=2)
            
            subscription = UserSubscription(
                id=uuid.uuid4(),
                user_id=user.id,
                plan_id=plan.id,
                status='active',  # 还没有被处理为expired
                start_date=past_start,
                end_date=past_end,
                auto_renew=False
            )
            db_session.add(subscription)
            db_session.commit()
            
            # 触发提醒发送
            response = client.post("/api/v1/admin/subscriptions/send-reminders")
            
            # 验证提醒发送成功（但不应该包含已过期的订阅）
            assert response.status_code == 200
            data = response.json()
            # 已过期的订阅不应该被提醒
            assert data["reminded"] == 0
        finally:
            db_session.close()
