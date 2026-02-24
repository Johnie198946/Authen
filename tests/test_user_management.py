"""
测试用户管理功能
验证需求：7.1

测试用户创建、更新、删除、搜索和过滤功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database import Base, get_db
from shared.models.user import User
from services.user.main import app
import uuid
from datetime import datetime

# 测试数据库
TEST_DATABASE_URL = "sqlite:///./test_user_management.db"
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

@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前重置数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session():
    """提供数据库会话"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestUserCreation:
    """测试用户创建功能"""
    
    def test_create_user_with_email(self):
        """测试使用邮箱创建用户"""
        response = client.post(
            "/api/v1/users",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "SecurePass123!"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert data["status"] == "active"
        assert "id" in data
        assert "created_at" in data
    
    def test_create_user_with_phone(self):
        """测试使用手机号创建用户"""
        response = client.post(
            "/api/v1/users",
            json={
                "username": "phoneuser",
                "phone": "+8613800138000",
                "password": "SecurePass123!"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "phoneuser"
        assert data["phone"] == "+8613800138000"
        assert data["status"] == "active"
    
    def test_create_user_with_both_email_and_phone(self):
        """测试同时使用邮箱和手机号创建用户"""
        response = client.post(
            "/api/v1/users",
            json={
                "username": "fulluser",
                "email": "full@example.com",
                "phone": "+8613900139000",
                "password": "SecurePass123!"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "full@example.com"
        assert data["phone"] == "+8613900139000"
    
    def test_create_user_without_email_or_phone(self):
        """测试创建用户时不提供邮箱或手机号（应该失败）"""
        response = client.post(
            "/api/v1/users",
            json={
                "username": "nocontact",
                "password": "SecurePass123!"
            }
        )
        
        assert response.status_code == 400
        assert "邮箱或手机号至少提供一个" in response.json()["detail"]

    
    def test_create_user_with_duplicate_email(self):
        """测试创建重复邮箱的用户（应该失败）"""
        # 创建第一个用户
        client.post(
            "/api/v1/users",
            json={
                "username": "user1",
                "email": "duplicate@example.com",
                "password": "SecurePass123!"
            }
        )
        
        # 尝试创建相同邮箱的用户
        response = client.post(
            "/api/v1/users",
            json={
                "username": "user2",
                "email": "duplicate@example.com",
                "password": "SecurePass123!"
            }
        )
        
        assert response.status_code == 409
        assert "邮箱已存在" in response.json()["detail"]
    
    def test_create_user_with_duplicate_phone(self):
        """测试创建重复手机号的用户（应该失败）"""
        # 创建第一个用户
        client.post(
            "/api/v1/users",
            json={
                "username": "user1",
                "phone": "+8613800138000",
                "password": "SecurePass123!"
            }
        )
        
        # 尝试创建相同手机号的用户
        response = client.post(
            "/api/v1/users",
            json={
                "username": "user2",
                "phone": "+8613800138000",
                "password": "SecurePass123!"
            }
        )
        
        assert response.status_code == 409
        assert "手机号已存在" in response.json()["detail"]
    
    def test_create_user_password_is_hashed(self, db_session):
        """测试创建用户时密码被正确加密"""
        password = "SecurePass123!"
        response = client.post(
            "/api/v1/users",
            json={
                "username": "hashtest",
                "email": "hash@example.com",
                "password": password
            }
        )
        
        assert response.status_code == 200
        user_id = response.json()["id"]
        
        # 从数据库查询用户
        user = db_session.query(User).filter(User.id == uuid.UUID(user_id)).first()
        assert user is not None
        assert user.password_hash != password
        # 密码哈希格式应该是 salt$hash
        assert "$" in user.password_hash
        parts = user.password_hash.split("$")
        assert len(parts) == 2
        assert len(parts[0]) == 32  # salt is 16 bytes hex = 32 chars
        assert len(parts[1]) == 64  # SHA256 hash is 32 bytes hex = 64 chars



class TestUserRetrieval:
    """测试用户查询功能"""
    
    def test_get_user_by_id(self, db_session):
        """测试通过ID获取用户"""
        # 创建测试用户
        user = User(
            id=uuid.uuid4(),
            username="gettest",
            email="get@example.com",
            password_hash="hashed",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        response = client.get(f"/api/v1/users/{user.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(user.id)
        assert data["username"] == "gettest"
        assert data["email"] == "get@example.com"
        assert data["status"] == "active"
    
    def test_get_nonexistent_user(self):
        """测试获取不存在的用户"""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/users/{fake_id}")
        
        assert response.status_code == 404
        assert "用户不存在" in response.json()["detail"]
    
    def test_get_user_does_not_expose_password(self, db_session):
        """测试获取用户时不暴露密码"""
        user = User(
            id=uuid.uuid4(),
            username="securetest",
            email="secure@example.com",
            password_hash="hashed_password",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        response = client.get(f"/api/v1/users/{user.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "password" not in data
        assert "password_hash" not in data



class TestUserUpdate:
    """测试用户更新功能"""
    
    def test_update_user_username(self, db_session):
        """测试更新用户名"""
        user = User(
            id=uuid.uuid4(),
            username="oldname",
            email="update@example.com",
            password_hash="hashed",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        response = client.put(
            f"/api/v1/users/{user.id}",
            json={"username": "newname"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "newname"
        assert data["email"] == "update@example.com"  # 其他字段不变
    
    def test_update_user_email(self, db_session):
        """测试更新邮箱"""
        user = User(
            id=uuid.uuid4(),
            username="emailtest",
            email="old@example.com",
            password_hash="hashed",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        response = client.put(
            f"/api/v1/users/{user.id}",
            json={"email": "new@example.com"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "new@example.com"
    
    def test_update_user_phone(self, db_session):
        """测试更新手机号"""
        user = User(
            id=uuid.uuid4(),
            username="phonetest",
            phone="+8613800138000",
            password_hash="hashed",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        response = client.put(
            f"/api/v1/users/{user.id}",
            json={"phone": "+8613900139000"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == "+8613900139000"
    
    def test_update_user_status(self, db_session):
        """测试更新用户状态"""
        user = User(
            id=uuid.uuid4(),
            username="statustest",
            email="status@example.com",
            password_hash="hashed",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        response = client.put(
            f"/api/v1/users/{user.id}",
            json={"status": "disabled"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disabled"

    
    def test_update_multiple_fields(self, db_session):
        """测试同时更新多个字段"""
        user = User(
            id=uuid.uuid4(),
            username="multitest",
            email="multi@example.com",
            password_hash="hashed",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        response = client.put(
            f"/api/v1/users/{user.id}",
            json={
                "username": "newmulti",
                "email": "newmulti@example.com",
                "status": "locked"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "newmulti"
        assert data["email"] == "newmulti@example.com"
        assert data["status"] == "locked"
    
    def test_update_nonexistent_user(self):
        """测试更新不存在的用户"""
        fake_id = str(uuid.uuid4())
        response = client.put(
            f"/api/v1/users/{fake_id}",
            json={"username": "newname"}
        )
        
        assert response.status_code == 404
        assert "用户不存在" in response.json()["detail"]
    
    def test_update_user_with_empty_data(self, db_session):
        """测试使用空数据更新用户（应该不改变任何内容）"""
        user = User(
            id=uuid.uuid4(),
            username="emptytest",
            email="empty@example.com",
            password_hash="hashed",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        response = client.put(
            f"/api/v1/users/{user.id}",
            json={}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "emptytest"
        assert data["email"] == "empty@example.com"
        assert data["status"] == "active"



class TestUserDeletion:
    """测试用户删除功能"""
    
    def test_delete_user(self, db_session):
        """测试删除用户"""
        user = User(
            id=uuid.uuid4(),
            username="deletetest",
            email="delete@example.com",
            password_hash="hashed",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        user_id = user.id
        
        response = client.delete(f"/api/v1/users/{user_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "已删除" in data["message"]
        
        # 验证用户已被删除
        deleted_user = db_session.query(User).filter(User.id == user_id).first()
        assert deleted_user is None
    
    def test_delete_nonexistent_user(self):
        """测试删除不存在的用户"""
        fake_id = str(uuid.uuid4())
        response = client.delete(f"/api/v1/users/{fake_id}")
        
        assert response.status_code == 404
        assert "用户不存在" in response.json()["detail"]
    
    def test_delete_user_is_permanent(self, db_session):
        """测试删除用户后无法再获取"""
        user = User(
            id=uuid.uuid4(),
            username="permanent",
            email="permanent@example.com",
            password_hash="hashed",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        user_id = user.id
        
        # 删除用户
        delete_response = client.delete(f"/api/v1/users/{user_id}")
        assert delete_response.status_code == 200
        
        # 尝试获取已删除的用户
        get_response = client.get(f"/api/v1/users/{user_id}")
        assert get_response.status_code == 404



class TestUserSearch:
    """测试用户搜索功能"""
    
    @pytest.fixture
    def sample_users(self, db_session):
        """创建示例用户数据"""
        users = [
            User(id=uuid.uuid4(), username="alice", email="alice@example.com", 
                 password_hash="hashed", status="active"),
            User(id=uuid.uuid4(), username="bob", email="bob@example.com", 
                 password_hash="hashed", status="active"),
            User(id=uuid.uuid4(), username="charlie", email="charlie@example.com", 
                 password_hash="hashed", status="locked"),
            User(id=uuid.uuid4(), username="david", phone="+8613800138000", 
                 password_hash="hashed", status="active"),
            User(id=uuid.uuid4(), username="eve", email="eve@test.com", 
                 password_hash="hashed", status="disabled"),
        ]
        for user in users:
            db_session.add(user)
        db_session.commit()
        return users
    
    def test_search_by_username(self, sample_users):
        """测试按用户名搜索"""
        response = client.get("/api/v1/users?search=alice")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(user["username"] == "alice" for user in data["users"])
    
    def test_search_by_email(self, sample_users):
        """测试按邮箱搜索"""
        response = client.get("/api/v1/users?search=bob@example.com")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(user["email"] == "bob@example.com" for user in data["users"])
    
    def test_search_by_phone(self, sample_users):
        """测试按手机号搜索"""
        response = client.get("/api/v1/users?search=13800138000")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(user["phone"] and "13800138000" in user["phone"] for user in data["users"])
    
    def test_search_partial_match(self, sample_users):
        """测试部分匹配搜索"""
        response = client.get("/api/v1/users?search=example.com")
        
        assert response.status_code == 200
        data = response.json()
        # 应该匹配所有 @example.com 的邮箱
        assert data["total"] >= 3
    
    def test_search_no_results(self, sample_users):
        """测试搜索无结果"""
        response = client.get("/api/v1/users?search=nonexistent")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["users"]) == 0



class TestUserFiltering:
    """测试用户过滤功能"""
    
    @pytest.fixture
    def sample_users(self, db_session):
        """创建示例用户数据"""
        users = [
            User(id=uuid.uuid4(), username="active1", email="active1@example.com", 
                 password_hash="hashed", status="active"),
            User(id=uuid.uuid4(), username="active2", email="active2@example.com", 
                 password_hash="hashed", status="active"),
            User(id=uuid.uuid4(), username="locked1", email="locked1@example.com", 
                 password_hash="hashed", status="locked"),
            User(id=uuid.uuid4(), username="disabled1", email="disabled1@example.com", 
                 password_hash="hashed", status="disabled"),
        ]
        for user in users:
            db_session.add(user)
        db_session.commit()
        return users
    
    def test_filter_by_active_status(self, sample_users):
        """测试过滤活跃用户"""
        response = client.get("/api/v1/users?status=active")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2
        assert all(user["status"] == "active" for user in data["users"])
    
    def test_filter_by_locked_status(self, sample_users):
        """测试过滤锁定用户"""
        response = client.get("/api/v1/users?status=locked")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(user["status"] == "locked" for user in data["users"])
    
    def test_filter_by_disabled_status(self, sample_users):
        """测试过滤禁用用户"""
        response = client.get("/api/v1/users?status=disabled")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(user["status"] == "disabled" for user in data["users"])
    
    def test_filter_and_search_combined(self, sample_users):
        """测试组合过滤和搜索"""
        response = client.get("/api/v1/users?status=active&search=active")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2
        assert all(user["status"] == "active" for user in data["users"])
        assert all("active" in user["username"] for user in data["users"])



class TestUserPagination:
    """测试用户列表分页功能"""
    
    @pytest.fixture
    def many_users(self, db_session):
        """创建大量用户用于分页测试"""
        users = []
        for i in range(50):
            user = User(
                id=uuid.uuid4(),
                username=f"user{i:03d}",
                email=f"user{i:03d}@example.com",
                password_hash="hashed",
                status="active"
            )
            db_session.add(user)
            users.append(user)
        db_session.commit()
        return users
    
    def test_default_pagination(self, many_users):
        """测试默认分页（第1页，每页20条）"""
        response = client.get("/api/v1/users")
        
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["users"]) == 20
        assert data["total"] == 50
    
    def test_custom_page_size(self, many_users):
        """测试自定义每页数量"""
        response = client.get("/api/v1/users?page_size=10")
        
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 10
        assert len(data["users"]) == 10
    
    def test_second_page(self, many_users):
        """测试获取第二页"""
        response = client.get("/api/v1/users?page=2&page_size=20")
        
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert len(data["users"]) == 20
    
    def test_last_page_partial(self, many_users):
        """测试最后一页（不足一页的情况）"""
        response = client.get("/api/v1/users?page=3&page_size=20")
        
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 3
        assert len(data["users"]) == 10  # 50 - 20 - 20 = 10
    
    def test_page_beyond_total(self, many_users):
        """测试超出总页数的页码"""
        response = client.get("/api/v1/users?page=10&page_size=20")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 0
    
    def test_max_page_size_limit(self, many_users):
        """测试每页数量上限（最大100）"""
        response = client.get("/api/v1/users?page_size=200")
        
        assert response.status_code == 422  # Validation error
    
    def test_invalid_page_number(self):
        """测试无效的页码（小于1）"""
        response = client.get("/api/v1/users?page=0")
        
        assert response.status_code == 422  # Validation error



class TestUserListResponse:
    """测试用户列表响应格式"""
    
    def test_empty_user_list(self):
        """测试空用户列表"""
        response = client.get("/api/v1/users")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["users"] == []
    
    def test_user_list_response_structure(self, db_session):
        """测试用户列表响应结构"""
        user = User(
            id=uuid.uuid4(),
            username="structuretest",
            email="structure@example.com",
            password_hash="hashed",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        response = client.get("/api/v1/users")
        
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "users" in data
        assert isinstance(data["users"], list)
        
        if len(data["users"]) > 0:
            user_data = data["users"][0]
            assert "id" in user_data
            assert "username" in user_data
            assert "email" in user_data
            assert "status" in user_data
            assert "created_at" in user_data
            # 确保不包含敏感信息
            assert "password" not in user_data
            assert "password_hash" not in user_data


class TestEdgeCases:
    """测试边界情况"""
    
    def test_create_user_with_very_long_username(self):
        """测试创建用户名过长的用户"""
        long_username = "a" * 100
        response = client.post(
            "/api/v1/users",
            json={
                "username": long_username,
                "email": "long@example.com",
                "password": "SecurePass123!"
            }
        )
        
        # 应该成功或返回验证错误，取决于模型定义
        assert response.status_code in [200, 422]
    
    def test_create_user_with_special_characters_in_username(self):
        """测试用户名包含特殊字符"""
        response = client.post(
            "/api/v1/users",
            json={
                "username": "user@#$%",
                "email": "special@example.com",
                "password": "SecurePass123!"
            }
        )
        
        # 应该成功创建（如果允许）或返回验证错误
        assert response.status_code in [200, 422]
    
    def test_update_user_to_invalid_status(self, db_session):
        """测试更新用户为无效状态"""
        user = User(
            id=uuid.uuid4(),
            username="statustest",
            email="status@example.com",
            password_hash="hashed",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        response = client.put(
            f"/api/v1/users/{user.id}",
            json={"status": "invalid_status"}
        )
        
        # 应该成功（如果没有验证）或返回验证错误
        assert response.status_code in [200, 422]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
