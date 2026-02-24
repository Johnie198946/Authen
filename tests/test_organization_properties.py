"""
组织架构服务属性测试

Feature: unified-auth-platform, Properties 21-24: 组织架构管理

验证需求：5.2, 5.3, 5.4, 5.5, 5.6
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
from shared.models.organization import Organization, UserOrganization, OrganizationPermission
from shared.models.user import User
from shared.models.permission import Permission
from services.organization.main import app
import uuid

# 测试数据库
TEST_DATABASE_URL = "sqlite:///./test_organization_properties.db"
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
org_names = st.text(
    alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs')),
    min_size=3,
    max_size=50
).filter(lambda x: x.strip())  # 过滤掉只有空格的字符串

@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前重置数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


class TestProperty21OrganizationNodeParentChildRelationship:
    """
    属性 21：组织节点父子关系
    
    对于任意组织节点，当创建时指定父节点，系统应该正确建立父子关系，
    且节点的path字段应该包含从根节点到当前节点的完整路径。
    
    **验证需求：5.2**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(org_name=org_names)
    def test_root_node_has_correct_path(self, org_name):
        """
        属性测试：根节点的路径正确
        
        给定：创建一个没有父节点的组织
        当：查询该组织
        则：path应该是 /组织名，level应该是0，parent_id应该是None
        """
        # 创建根组织
        response = client.post(
            "/api/v1/organizations",
            json={"name": org_name, "parent_id": None}
        )
        
        # 验证
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == org_name
        assert data["parent_id"] is None
        assert data["path"] == f"/{org_name}"
        assert data["level"] == 0
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        parent_name=org_names,
        child_name=org_names
    )
    def test_child_node_inherits_parent_path(self, parent_name, child_name):
        """
        属性测试：子节点继承父节点路径
        
        给定：创建父节点和子节点
        当：查询子节点
        则：子节点的path应该是 父节点path/子节点名，level应该是父节点level+1
        """
        # 创建父组织
        parent_response = client.post(
            "/api/v1/organizations",
            json={"name": parent_name, "parent_id": None}
        )
        assert parent_response.status_code == 200
        parent_data = parent_response.json()
        parent_id = parent_data["id"]
        
        # 创建子组织
        child_response = client.post(
            "/api/v1/organizations",
            json={"name": child_name, "parent_id": parent_id}
        )
        
        # 验证
        assert child_response.status_code == 200
        child_data = child_response.json()
        assert child_data["name"] == child_name
        assert child_data["parent_id"] == parent_id
        assert child_data["path"] == f"/{parent_name}/{child_name}"
        assert child_data["level"] == 1
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        num_levels=st.integers(min_value=2, max_value=5)
    )
    def test_deep_hierarchy_path_correctness(self, num_levels):
        """
        属性测试：深层级组织路径正确性
        
        给定：创建多层级的组织结构
        当：查询最深层的节点
        则：path应该包含从根到该节点的完整路径，level应该正确
        """
        parent_id = None
        expected_path_parts = []
        
        # 创建多层级组织
        for level in range(num_levels):
            org_name = f"org_level_{level}_{uuid.uuid4().hex[:8]}"
            expected_path_parts.append(org_name)
            
            response = client.post(
                "/api/v1/organizations",
                json={"name": org_name, "parent_id": parent_id}
            )
            
            assert response.status_code == 200
            data = response.json()
            parent_id = data["id"]
            
            # 验证路径和层级
            expected_path = "/" + "/".join(expected_path_parts)
            assert data["path"] == expected_path
            assert data["level"] == level
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        parent_name=org_names,
        num_children=st.integers(min_value=2, max_value=5)
    )
    def test_multiple_children_same_parent(self, parent_name, num_children):
        """
        属性测试：同一父节点的多个子节点
        
        给定：一个父节点和多个子节点
        当：创建所有子节点
        则：所有子节点应该有相同的parent_id和level，但path不同
        """
        # 创建父组织
        parent_response = client.post(
            "/api/v1/organizations",
            json={"name": parent_name, "parent_id": None}
        )
        assert parent_response.status_code == 200
        parent_id = parent_response.json()["id"]
        
        # 创建多个子组织
        children_data = []
        for i in range(num_children):
            child_name = f"child_{i}_{uuid.uuid4().hex[:8]}"
            child_response = client.post(
                "/api/v1/organizations",
                json={"name": child_name, "parent_id": parent_id}
            )
            assert child_response.status_code == 200
            children_data.append(child_response.json())
        
        # 验证所有子节点
        for child_data in children_data:
            assert child_data["parent_id"] == parent_id
            assert child_data["level"] == 1
            assert child_data["path"].startswith(f"/{parent_name}/")
        
        # 验证所有子节点的path都不同
        paths = [child["path"] for child in children_data]
        assert len(paths) == len(set(paths))
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(org_name=org_names)
    def test_organization_tree_structure(self, org_name):
        """
        属性测试：组织树结构查询
        
        给定：创建一个组织节点
        当：查询组织树
        则：应该能在树结构中找到该节点
        """
        # 创建组织
        create_response = client.post(
            "/api/v1/organizations",
            json={"name": org_name, "parent_id": None}
        )
        assert create_response.status_code == 200
        org_id = create_response.json()["id"]
        
        # 查询组织树
        tree_response = client.get("/api/v1/organizations/tree")
        assert tree_response.status_code == 200
        tree = tree_response.json()
        
        # 验证组织在树中
        def find_org_in_tree(nodes, target_id):
            for node in nodes:
                if node["id"] == target_id:
                    return True
                if node.get("children") and find_org_in_tree(node["children"], target_id):
                    return True
            return False
        
        assert find_org_in_tree(tree, org_id)


class TestProperty22UserOrganizationMembership:
    """
    属性 22：用户组织归属
    
    对于任意用户和组织节点，当管理员将用户分配到组织时，
    系统应该正确记录用户的组织归属关系。
    
    **验证需求：5.3**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        org_name=org_names,
        num_users=st.integers(min_value=1, max_value=5)
    )
    def test_assign_users_to_organization(self, org_name, num_users):
        """
        属性测试：分配用户到组织
        
        给定：一个组织和多个用户
        当：将用户分配到组织
        则：应该成功创建用户-组织关联
        """
        db_session = TestingSessionLocal()
        try:
            # 创建组织
            org_response = client.post(
                "/api/v1/organizations",
                json={"name": org_name, "parent_id": None}
            )
            assert org_response.status_code == 200
            org_id = org_response.json()["id"]
            
            # 创建用户
            user_ids = []
            for i in range(num_users):
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
            
            # 分配用户到组织
            assign_response = client.post(
                f"/api/v1/organizations/{org_id}/users",
                json=user_ids
            )
            
            # 验证
            assert assign_response.status_code == 200
            assert assign_response.json()["success"] is True
            
            # 验证数据库中的关联
            for user_id in user_ids:
                user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
                org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
                user_org = db_session.query(UserOrganization).filter(
                    UserOrganization.user_id == user_uuid,
                    UserOrganization.organization_id == org_uuid
                ).first()
                assert user_org is not None
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(org_name=org_names)
    def test_assign_same_user_twice_is_idempotent(self, org_name):
        """
        属性测试：重复分配用户是幂等的
        
        给定：用户已经在组织中
        当：再次分配该用户到同一组织
        则：应该成功但不创建重复记录
        """
        db_session = TestingSessionLocal()
        try:
            # 创建组织
            org_response = client.post(
                "/api/v1/organizations",
                json={"name": org_name, "parent_id": None}
            )
            assert org_response.status_code == 200
            org_id = org_response.json()["id"]
            
            # 创建用户
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
            
            # 第一次分配
            response1 = client.post(
                f"/api/v1/organizations/{org_id}/users",
                json=[user_id]
            )
            assert response1.status_code == 200
            
            # 第二次分配（重复）
            response2 = client.post(
                f"/api/v1/organizations/{org_id}/users",
                json=[user_id]
            )
            assert response2.status_code == 200
            
            # 验证只有一条记录
            user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
            org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
            count = db_session.query(UserOrganization).filter(
                UserOrganization.user_id == user_uuid,
                UserOrganization.organization_id == org_uuid
            ).count()
            assert count == 1
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        num_orgs=st.integers(min_value=2, max_value=4)
    )
    def test_user_can_belong_to_multiple_organizations(self, num_orgs):
        """
        属性测试：用户可以属于多个组织
        
        给定：多个组织和一个用户
        当：将用户分配到所有组织
        则：用户应该属于所有这些组织
        """
        db_session = TestingSessionLocal()
        try:
            # 创建用户
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
            
            # 创建多个组织并分配用户
            org_ids = []
            for i in range(num_orgs):
                org_name = f"org_{i}_{uuid.uuid4().hex[:8]}"
                org_response = client.post(
                    "/api/v1/organizations",
                    json={"name": org_name, "parent_id": None}
                )
                assert org_response.status_code == 200
                org_id = org_response.json()["id"]
                org_ids.append(org_id)
                
                # 分配用户到组织
                assign_response = client.post(
                    f"/api/v1/organizations/{org_id}/users",
                    json=[user_id]
                )
                assert assign_response.status_code == 200
            
            # 验证用户属于所有组织
            user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
            for org_id in org_ids:
                org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
                user_org = db_session.query(UserOrganization).filter(
                    UserOrganization.user_id == user_uuid,
                    UserOrganization.organization_id == org_uuid
                ).first()
                assert user_org is not None
        finally:
            db_session.close()




class TestProperty24OrganizationMovePermissionUpdate:
    """
    属性 24：组织移动权限更新
    
    对于任意组织节点，当管理员将其移动到新的父节点下时，
    该节点及其子节点的所有用户的权限应该根据新的继承关系重新计算。
    
    **验证需求：5.5**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        org_a_name=org_names,
        org_b_name=org_names,
        org_c_name=org_names
    )
    def test_move_organization_updates_permission_inheritance(self, org_a_name, org_b_name, org_c_name):
        """
        属性测试：移动组织更新权限继承
        
        给定：组织A有权限P1，组织B有权限P2，组织C是B的子节点
        当：将组织C移动到A下
        则：组织C应该继承A的权限P1，而不再继承B的权限P2
        """
        db_session = TestingSessionLocal()
        try:
            # 创建组织A（根节点）
            org_a_response = client.post(
                "/api/v1/organizations",
                json={"name": org_a_name, "parent_id": None}
            )
            assert org_a_response.status_code == 200
            org_a_id = org_a_response.json()["id"]
            
            # 创建组织B（根节点）
            org_b_response = client.post(
                "/api/v1/organizations",
                json={"name": org_b_name, "parent_id": None}
            )
            assert org_b_response.status_code == 200
            org_b_id = org_b_response.json()["id"]
            
            # 创建组织C（B的子节点）
            org_c_response = client.post(
                "/api/v1/organizations",
                json={"name": org_c_name, "parent_id": org_b_id}
            )
            assert org_c_response.status_code == 200
            org_c_id = org_c_response.json()["id"]
            
            # 创建权限P1并分配给组织A
            perm_p1 = Permission(
                id=uuid.uuid4(),
                name=f"test:perm_p1_{uuid.uuid4().hex[:8]}",
                resource="test",
                action="read",
                description="Permission P1"
            )
            db_session.add(perm_p1)
            db_session.commit()
            db_session.refresh(perm_p1)
            perm_p1_id = str(perm_p1.id)
            
            # 创建权限P2并分配给组织B
            perm_p2 = Permission(
                id=uuid.uuid4(),
                name=f"test:perm_p2_{uuid.uuid4().hex[:8]}",
                resource="test",
                action="write",
                description="Permission P2"
            )
            db_session.add(perm_p2)
            db_session.commit()
            db_session.refresh(perm_p2)
            perm_p2_id = str(perm_p2.id)
            
            # 分配权限
            client.post(f"/api/v1/organizations/{org_a_id}/permissions", json=[perm_p1_id])
            client.post(f"/api/v1/organizations/{org_b_id}/permissions", json=[perm_p2_id])
            
            # 移动前：C应该继承B的权限P2
            perms_before = client.get(
                f"/api/v1/organizations/{org_c_id}/permissions?include_inherited=true"
            ).json()
            assert perm_p2_id in perms_before["permission_ids"]
            assert perm_p1_id not in perms_before["permission_ids"]
            
            # 移动组织C到A下
            move_response = client.put(
                f"/api/v1/organizations/{org_c_id}/move",
                json={"new_parent_id": org_a_id}
            )
            assert move_response.status_code == 200
            
            # 移动后：C应该继承A的权限P1，不再继承B的权限P2
            perms_after = client.get(
                f"/api/v1/organizations/{org_c_id}/permissions?include_inherited=true"
            ).json()
            assert perm_p1_id in perms_after["permission_ids"]
            assert perm_p2_id not in perms_after["permission_ids"]
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        num_children=st.integers(min_value=2, max_value=4)
    )
    def test_move_organization_with_children_updates_all_paths(self, num_children):
        """
        属性测试：移动带子节点的组织更新所有路径
        
        给定：组织A有多个子节点
        当：将组织A移动到新父节点下
        则：A及其所有子节点的path和level都应该正确更新
        """
        db_session = TestingSessionLocal()
        try:
            # 创建根组织A
            org_a_response = client.post(
                "/api/v1/organizations",
                json={"name": f"org_a_{uuid.uuid4().hex[:8]}", "parent_id": None}
            )
            assert org_a_response.status_code == 200
            org_a_id = org_a_response.json()["id"]
            org_a_name = org_a_response.json()["name"]
            
            # 创建A的多个子节点
            child_ids = []
            child_names = []
            for i in range(num_children):
                child_name = f"child_{i}_{uuid.uuid4().hex[:8]}"
                child_response = client.post(
                    "/api/v1/organizations",
                    json={"name": child_name, "parent_id": org_a_id}
                )
                assert child_response.status_code == 200
                child_ids.append(child_response.json()["id"])
                child_names.append(child_name)
            
            # 创建新的根组织B
            org_b_response = client.post(
                "/api/v1/organizations",
                json={"name": f"org_b_{uuid.uuid4().hex[:8]}", "parent_id": None}
            )
            assert org_b_response.status_code == 200
            org_b_id = org_b_response.json()["id"]
            org_b_name = org_b_response.json()["name"]
            
            # 移动A到B下
            move_response = client.put(
                f"/api/v1/organizations/{org_a_id}/move",
                json={"new_parent_id": org_b_id}
            )
            assert move_response.status_code == 200
            
            # 验证A的path和level
            org_a_after = move_response.json()
            assert org_a_after["path"] == f"/{org_b_name}/{org_a_name}"
            assert org_a_after["level"] == 1
            
            # 验证所有子节点的path和level
            for i, child_id in enumerate(child_ids):
                child_org = db_session.query(Organization).filter(
                    Organization.id == uuid.UUID(child_id)
                ).first()
                assert child_org is not None
                assert child_org.path == f"/{org_b_name}/{org_a_name}/{child_names[i]}"
                assert child_org.level == 2
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(org_name=org_names)
    def test_cannot_move_organization_to_itself(self, org_name):
        """
        属性测试：不能将组织移动到自己
        
        给定：一个组织
        当：尝试将组织移动到自己
        则：应该返回错误
        """
        # 创建组织
        org_response = client.post(
            "/api/v1/organizations",
            json={"name": org_name, "parent_id": None}
        )
        assert org_response.status_code == 200
        org_id = org_response.json()["id"]
        
        # 尝试移动到自己
        move_response = client.put(
            f"/api/v1/organizations/{org_id}/move",
            json={"new_parent_id": org_id}
        )
        
        # 应该返回错误
        assert move_response.status_code == 400
        assert "不能将组织移动到自己" in move_response.json()["detail"]
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        parent_name=org_names,
        child_name=org_names
    )
    def test_cannot_move_organization_to_its_descendant(self, parent_name, child_name):
        """
        属性测试：不能将组织移动到自己的子孙节点
        
        给定：父组织和子组织
        当：尝试将父组织移动到子组织下
        则：应该返回错误（避免循环）
        """
        # 创建父组织
        parent_response = client.post(
            "/api/v1/organizations",
            json={"name": parent_name, "parent_id": None}
        )
        assert parent_response.status_code == 200
        parent_id = parent_response.json()["id"]
        
        # 创建子组织
        child_response = client.post(
            "/api/v1/organizations",
            json={"name": child_name, "parent_id": parent_id}
        )
        assert child_response.status_code == 200
        child_id = child_response.json()["id"]
        
        # 尝试将父组织移动到子组织下
        move_response = client.put(
            f"/api/v1/organizations/{parent_id}/move",
            json={"new_parent_id": child_id}
        )
        
        # 应该返回错误
        assert move_response.status_code == 400
        assert "不能将组织移动到自己的子节点" in move_response.json()["detail"]
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(org_name=org_names)
    def test_move_organization_to_root(self, org_name):
        """
        属性测试：将组织移动到根级别
        
        给定：一个子组织
        当：将其移动到根级别（parent_id=None）
        则：组织应该成为根节点，path和level正确更新
        """
        db_session = TestingSessionLocal()
        try:
            # 创建父组织
            parent_response = client.post(
                "/api/v1/organizations",
                json={"name": f"parent_{uuid.uuid4().hex[:8]}", "parent_id": None}
            )
            assert parent_response.status_code == 200
            parent_id = parent_response.json()["id"]
            
            # 创建子组织
            child_response = client.post(
                "/api/v1/organizations",
                json={"name": org_name, "parent_id": parent_id}
            )
            assert child_response.status_code == 200
            child_id = child_response.json()["id"]
            
            # 移动到根级别
            move_response = client.put(
                f"/api/v1/organizations/{child_id}/move",
                json={"new_parent_id": None}
            )
            assert move_response.status_code == 200
            
            # 验证
            moved_org = move_response.json()
            assert moved_org["parent_id"] is None
            assert moved_org["path"] == f"/{org_name}"
            assert moved_org["level"] == 0
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        num_levels=st.integers(min_value=9, max_value=10)
    )
    def test_move_respects_max_depth_limit(self, num_levels):
        """
        属性测试：移动组织时遵守最大深度限制
        
        给定：一个深层级的组织结构（接近10层）
        当：尝试移动使其超过10层
        则：应该返回错误
        """
        db_session = TestingSessionLocal()
        try:
            # 创建深层级组织结构 (num_levels个节点，最深层级是num_levels-1)
            parent_id = None
            org_ids = []
            for level in range(num_levels):
                org_name = f"org_level_{level}_{uuid.uuid4().hex[:8]}"
                response = client.post(
                    "/api/v1/organizations",
                    json={"name": org_name, "parent_id": parent_id}
                )
                assert response.status_code == 200
                org_id = response.json()["id"]
                org_ids.append(org_id)
                parent_id = org_id
            
            # 创建另一个深层级结构 (3个节点，最深层级是2)
            target_parent_id = None
            for level in range(3):
                org_name = f"target_level_{level}_{uuid.uuid4().hex[:8]}"
                response = client.post(
                    "/api/v1/organizations",
                    json={"name": org_name, "parent_id": target_parent_id}
                )
                assert response.status_code == 200
                target_parent_id = response.json()["id"]
            
            # 尝试将第一个结构的根节点移动到第二个结构下
            # 第一个结构的根节点当前在level 0，移动后会在level 3
            # 第一个结构最深的节点当前在level num_levels-1，移动后会在level 3+num_levels-1
            # 当num_levels=9时，移动后最深层级是3+8=11，超过10层
            # 当num_levels=10时，移动后最深层级是3+9=12，超过10层
            move_response = client.put(
                f"/api/v1/organizations/{org_ids[0]}/move",
                json={"new_parent_id": target_parent_id}
            )
            
            # 应该返回错误
            assert move_response.status_code == 400
            assert "层级" in move_response.json()["detail"] and "10" in move_response.json()["detail"]
        finally:
            db_session.close()




class TestOrganizationHierarchyDepthBoundary:
    """
    组织层级深度边界测试
    
    测试10层组织结构和超过10层的错误处理
    
    **验证需求：5.6**
    """
    
    def test_create_10_level_organization_structure(self):
        """
        边界测试：创建10层组织结构
        
        给定：无
        当：创建10层组织结构（level 0-9）
        则：所有组织都应该成功创建
        """
        db_session = TestingSessionLocal()
        try:
            parent_id = None
            org_ids = []
            
            # 创建10层组织（level 0-9）
            for level in range(10):
                org_name = f"org_level_{level}_{uuid.uuid4().hex[:8]}"
                response = client.post(
                    "/api/v1/organizations",
                    json={"name": org_name, "parent_id": parent_id}
                )
                
                # 所有10层都应该成功创建
                assert response.status_code == 200
                data = response.json()
                assert data["level"] == level
                org_ids.append(data["id"])
                parent_id = data["id"]
            
            # 验证最深层的组织
            deepest_org = db_session.query(Organization).filter(
                Organization.id == uuid.UUID(org_ids[-1])
            ).first()
            assert deepest_org is not None
            assert deepest_org.level == 9
            
            # 验证路径包含所有10层
            path_parts = deepest_org.path.split("/")
            # path以/开头，所以第一个元素是空字符串
            assert len(path_parts) == 11  # 空字符串 + 10层
        finally:
            db_session.close()
    
    def test_cannot_create_11th_level(self):
        """
        边界测试：不能创建第11层
        
        给定：已有10层组织结构
        当：尝试在第10层下创建子组织
        则：应该返回错误
        """
        db_session = TestingSessionLocal()
        try:
            parent_id = None
            
            # 创建10层组织（level 0-9）
            for level in range(10):
                org_name = f"org_level_{level}_{uuid.uuid4().hex[:8]}"
                response = client.post(
                    "/api/v1/organizations",
                    json={"name": org_name, "parent_id": parent_id}
                )
                assert response.status_code == 200
                parent_id = response.json()["id"]
            
            # 尝试创建第11层（level 10）
            response = client.post(
                "/api/v1/organizations",
                json={"name": f"org_level_10_{uuid.uuid4().hex[:8]}", "parent_id": parent_id}
            )
            
            # 应该返回错误
            assert response.status_code == 400
            assert "层级" in response.json()["detail"]
            assert "10" in response.json()["detail"]
        finally:
            db_session.close()
    
    def test_exactly_10_levels_is_allowed(self):
        """
        边界测试：恰好10层是允许的
        
        给定：无
        当：创建恰好10层的组织结构
        则：第10层（level 9）应该成功创建
        """
        db_session = TestingSessionLocal()
        try:
            parent_id = None
            
            # 创建9层组织（level 0-8）
            for level in range(9):
                org_name = f"org_level_{level}_{uuid.uuid4().hex[:8]}"
                response = client.post(
                    "/api/v1/organizations",
                    json={"name": org_name, "parent_id": parent_id}
                )
                assert response.status_code == 200
                parent_id = response.json()["id"]
            
            # 创建第10层（level 9）- 应该成功
            response = client.post(
                "/api/v1/organizations",
                json={"name": f"org_level_9_{uuid.uuid4().hex[:8]}", "parent_id": parent_id}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["level"] == 9
        finally:
            db_session.close()
    
    def test_multiple_branches_at_max_depth(self):
        """
        边界测试：多个分支都达到最大深度
        
        给定：一个根组织
        当：创建多个分支，每个分支都有10层
        则：所有分支都应该成功创建
        """
        db_session = TestingSessionLocal()
        try:
            # 创建根组织
            root_response = client.post(
                "/api/v1/organizations",
                json={"name": f"root_{uuid.uuid4().hex[:8]}", "parent_id": None}
            )
            assert root_response.status_code == 200
            root_id = root_response.json()["id"]
            
            # 创建3个分支，每个分支9层（加上根节点共10层）
            for branch in range(3):
                parent_id = root_id
                for level in range(1, 10):
                    org_name = f"branch_{branch}_level_{level}_{uuid.uuid4().hex[:8]}"
                    response = client.post(
                        "/api/v1/organizations",
                        json={"name": org_name, "parent_id": parent_id}
                    )
                    assert response.status_code == 200
                    assert response.json()["level"] == level
                    parent_id = response.json()["id"]
        finally:
            db_session.close()
    
    def test_error_message_is_clear(self):
        """
        边界测试：错误消息清晰明确
        
        给定：已有10层组织结构
        当：尝试创建第11层
        则：错误消息应该明确说明层级限制
        """
        db_session = TestingSessionLocal()
        try:
            parent_id = None
            
            # 创建10层组织
            for level in range(10):
                org_name = f"org_level_{level}_{uuid.uuid4().hex[:8]}"
                response = client.post(
                    "/api/v1/organizations",
                    json={"name": org_name, "parent_id": parent_id}
                )
                assert response.status_code == 200
                parent_id = response.json()["id"]
            
            # 尝试创建第11层
            response = client.post(
                "/api/v1/organizations",
                json={"name": f"org_level_10_{uuid.uuid4().hex[:8]}", "parent_id": parent_id}
            )
            
            # 验证错误消息
            assert response.status_code == 400
            error_detail = response.json()["detail"]
            assert "组织层级不能超过10层" == error_detail
        finally:
            db_session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])



class TestProperty23OrganizationPermissionInheritance:
    """
    属性 23：组织权限继承
    
    对于任意组织节点，当管理员为该节点设置权限时，
    该节点及其所有子节点的用户都应该继承这些权限。
    
    **验证需求：5.4**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        parent_name=org_names,
        child_name=org_names,
        num_permissions=st.integers(min_value=1, max_value=3)
    )
    def test_child_inherits_parent_permissions(self, parent_name, child_name, num_permissions):
        """
        属性测试：子节点继承父节点权限
        
        给定：父节点有权限，子节点没有直接权限
        当：查询子节点的权限（包括继承）
        则：子节点应该拥有父节点的所有权限
        """
        db_session = TestingSessionLocal()
        try:
            # 创建父组织
            parent_response = client.post(
                "/api/v1/organizations",
                json={"name": parent_name, "parent_id": None}
            )
            assert parent_response.status_code == 200
            parent_id = parent_response.json()["id"]
            
            # 创建子组织
            child_response = client.post(
                "/api/v1/organizations",
                json={"name": child_name, "parent_id": parent_id}
            )
            assert child_response.status_code == 200
            child_id = child_response.json()["id"]
            
            # 创建权限并分配给父组织
            permission_ids = []
            for i in range(num_permissions):
                perm = Permission(
                    id=uuid.uuid4(),
                    name=f"test:perm_{uuid.uuid4().hex[:8]}",
                    resource="test",
                    action=f"action_{i}",
                    description=f"Test permission {i}"
                )
                db_session.add(perm)
                db_session.commit()
                db_session.refresh(perm)
                permission_ids.append(str(perm.id))
            
            # 分配权限给父组织
            assign_response = client.post(
                f"/api/v1/organizations/{parent_id}/permissions",
                json=permission_ids
            )
            assert assign_response.status_code == 200
            
            # 查询子组织的权限（包括继承）
            child_perms_response = client.get(
                f"/api/v1/organizations/{child_id}/permissions?include_inherited=true"
            )
            assert child_perms_response.status_code == 200
            child_perms = child_perms_response.json()
            
            # 子组织应该继承父组织的所有权限
            assert len(child_perms["permission_ids"]) == num_permissions
            assert set(child_perms["permission_ids"]) == set(permission_ids)
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        num_levels=st.integers(min_value=2, max_value=4)
    )
    def test_deep_hierarchy_permission_inheritance(self, num_levels):
        """
        属性测试：深层级权限继承
        
        给定：多层级组织结构，根节点有权限
        当：查询最深层节点的权限
        则：最深层节点应该继承根节点的权限
        """
        db_session = TestingSessionLocal()
        try:
            # 创建多层级组织
            parent_id = None
            org_ids = []
            for level in range(num_levels):
                org_name = f"org_level_{level}_{uuid.uuid4().hex[:8]}"
                response = client.post(
                    "/api/v1/organizations",
                    json={"name": org_name, "parent_id": parent_id}
                )
                assert response.status_code == 200
                org_id = response.json()["id"]
                org_ids.append(org_id)
                parent_id = org_id
            
            # 创建权限并分配给根节点
            perm = Permission(
                id=uuid.uuid4(),
                name=f"test:perm_{uuid.uuid4().hex[:8]}",
                resource="test",
                action="read",
                description="Test permission"
            )
            db_session.add(perm)
            db_session.commit()
            db_session.refresh(perm)
            perm_id = str(perm.id)
            
            # 分配权限给根节点
            assign_response = client.post(
                f"/api/v1/organizations/{org_ids[0]}/permissions",
                json=[perm_id]
            )
            assert assign_response.status_code == 200
            
            # 查询最深层节点的权限
            deepest_perms_response = client.get(
                f"/api/v1/organizations/{org_ids[-1]}/permissions?include_inherited=true"
            )
            assert deepest_perms_response.status_code == 200
            deepest_perms = deepest_perms_response.json()
            
            # 最深层节点应该继承根节点的权限
            assert perm_id in deepest_perms["permission_ids"]
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        parent_name=org_names,
        child_name=org_names
    )
    def test_direct_and_inherited_permissions_combined(self, parent_name, child_name):
        """
        属性测试：直接权限和继承权限合并
        
        给定：父节点有权限A，子节点有权限B
        当：查询子节点的权限（包括继承）
        则：子节点应该同时拥有权限A和B
        """
        db_session = TestingSessionLocal()
        try:
            # 创建父组织
            parent_response = client.post(
                "/api/v1/organizations",
                json={"name": parent_name, "parent_id": None}
            )
            assert parent_response.status_code == 200
            parent_id = parent_response.json()["id"]
            
            # 创建子组织
            child_response = client.post(
                "/api/v1/organizations",
                json={"name": child_name, "parent_id": parent_id}
            )
            assert child_response.status_code == 200
            child_id = child_response.json()["id"]
            
            # 创建权限A并分配给父组织
            perm_a = Permission(
                id=uuid.uuid4(),
                name=f"test:perm_a_{uuid.uuid4().hex[:8]}",
                resource="test",
                action="read",
                description="Test permission A"
            )
            db_session.add(perm_a)
            db_session.commit()
            db_session.refresh(perm_a)
            perm_a_id = str(perm_a.id)
            
            # 创建权限B并分配给子组织
            perm_b = Permission(
                id=uuid.uuid4(),
                name=f"test:perm_b_{uuid.uuid4().hex[:8]}",
                resource="test",
                action="write",
                description="Test permission B"
            )
            db_session.add(perm_b)
            db_session.commit()
            db_session.refresh(perm_b)
            perm_b_id = str(perm_b.id)
            
            # 分配权限A给父组织
            client.post(
                f"/api/v1/organizations/{parent_id}/permissions",
                json=[perm_a_id]
            )
            
            # 分配权限B给子组织
            client.post(
                f"/api/v1/organizations/{child_id}/permissions",
                json=[perm_b_id]
            )
            
            # 查询子组织的权限（包括继承）
            child_perms_response = client.get(
                f"/api/v1/organizations/{child_id}/permissions?include_inherited=true"
            )
            assert child_perms_response.status_code == 200
            child_perms = child_perms_response.json()
            
            # 子组织应该同时拥有权限A和B
            assert len(child_perms["permission_ids"]) == 2
            assert perm_a_id in child_perms["permission_ids"]
            assert perm_b_id in child_perms["permission_ids"]
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(org_name=org_names)
    def test_no_inheritance_when_disabled(self, org_name):
        """
        属性测试：禁用继承时只返回直接权限
        
        给定：父节点有权限，子节点没有直接权限
        当：查询子节点的权限（不包括继承）
        则：子节点应该没有任何权限
        """
        db_session = TestingSessionLocal()
        try:
            # 创建父组织
            parent_response = client.post(
                "/api/v1/organizations",
                json={"name": f"parent_{org_name}", "parent_id": None}
            )
            assert parent_response.status_code == 200
            parent_id = parent_response.json()["id"]
            
            # 创建子组织
            child_response = client.post(
                "/api/v1/organizations",
                json={"name": f"child_{org_name}", "parent_id": parent_id}
            )
            assert child_response.status_code == 200
            child_id = child_response.json()["id"]
            
            # 创建权限并分配给父组织
            perm = Permission(
                id=uuid.uuid4(),
                name=f"test:perm_{uuid.uuid4().hex[:8]}",
                resource="test",
                action="read",
                description="Test permission"
            )
            db_session.add(perm)
            db_session.commit()
            db_session.refresh(perm)
            
            client.post(
                f"/api/v1/organizations/{parent_id}/permissions",
                json=[str(perm.id)]
            )
            
            # 查询子组织的权限（不包括继承）
            child_perms_response = client.get(
                f"/api/v1/organizations/{child_id}/permissions?include_inherited=false"
            )
            assert child_perms_response.status_code == 200
            child_perms = child_perms_response.json()
            
            # 子组织应该没有任何权限
            assert len(child_perms["permission_ids"]) == 0
        finally:
            db_session.close()
