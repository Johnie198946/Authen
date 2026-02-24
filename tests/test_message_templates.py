"""
消息模板管理测试

测试消息模板的CRUD操作、模板变量替换和验证逻辑。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import uuid

from services.admin.main import app
from shared.database import Base, get_db
from shared.models.user import User
from shared.models.permission import Role, UserRole
from shared.models.system import MessageTemplate
from shared.utils.crypto import hash_password

# 创建测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_message_templates.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """覆盖数据库依赖"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def db():
    """创建测试数据库"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


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
        password_hash=hash_password("admin123"),
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
        username="user",
        email="user@example.com",
        password_hash=hash_password("user123"),
        status="active"
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


class TestMessageTemplateList:
    """测试消息模板列表查询"""
    
    def test_list_templates_empty(self, client, super_admin_user):
        """测试查询空模板列表"""
        response = client.get(
            "/api/v1/admin/templates",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["templates"] == []
    
    def test_list_templates_with_data(self, client, super_admin_user, db):
        """测试查询包含数据的模板列表"""
        # 创建测试模板
        template1 = MessageTemplate(
            name="email_verification",
            type="email",
            subject="验证您的邮箱",
            content="<p>请点击链接验证：{{verification_link}}</p>",
            variables={"verification_link": "验证链接"}
        )
        template2 = MessageTemplate(
            name="sms_verification",
            type="sms",
            content="您的验证码是{{code}}，5分钟内有效。",
            variables={"code": "验证码"}
        )
        db.add_all([template1, template2])
        db.commit()
        
        response = client.get(
            "/api/v1/admin/templates",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["templates"]) == 2
    
    def test_list_templates_filter_by_type(self, client, super_admin_user, db):
        """测试按类型过滤模板列表"""
        # 创建不同类型的模板
        email_template = MessageTemplate(
            name="email_test",
            type="email",
            subject="测试邮件",
            content="测试内容"
        )
        sms_template = MessageTemplate(
            name="sms_test",
            type="sms",
            content="测试短信"
        )
        db.add_all([email_template, sms_template])
        db.commit()
        
        # 过滤邮件模板
        response = client.get(
            "/api/v1/admin/templates",
            params={"user_id": str(super_admin_user.id), "type": "email"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["templates"][0]["type"] == "email"
        
        # 过滤短信模板
        response = client.get(
            "/api/v1/admin/templates",
            params={"user_id": str(super_admin_user.id), "type": "sms"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["templates"][0]["type"] == "sms"
    
    def test_list_templates_invalid_type(self, client, super_admin_user):
        """测试使用无效类型过滤"""
        response = client.get(
            "/api/v1/admin/templates",
            params={"user_id": str(super_admin_user.id), "type": "invalid"}
        )
        
        assert response.status_code == 400
        assert "无效的模板类型" in response.json()["detail"]
    
    def test_list_templates_requires_super_admin(self, client, regular_user):
        """测试非超级管理员无法访问"""
        response = client.get(
            "/api/v1/admin/templates",
            params={"user_id": str(regular_user.id)}
        )
        
        assert response.status_code == 403
        assert "超级管理员" in response.json()["detail"]


class TestMessageTemplateCreate:
    """测试消息模板创建"""
    
    def test_create_email_template(self, client, super_admin_user, db):
        """测试创建邮件模板"""
        template_data = {
            "name": "welcome_email",
            "type": "email",
            "subject": "欢迎加入 {{app_name}}",
            "content": "<h1>欢迎，{{username}}！</h1><p>感谢您注册 {{app_name}}。</p>",
            "variables": {
                "app_name": "应用名称",
                "username": "用户名"
            }
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "welcome_email"
        assert data["type"] == "email"
        assert data["subject"] == template_data["subject"]
        assert data["content"] == template_data["content"]
        assert data["variables"] == template_data["variables"]
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data
        
        # 验证数据库中已创建
        template = db.query(MessageTemplate).filter(
            MessageTemplate.name == "welcome_email"
        ).first()
        assert template is not None
        assert template.type == "email"
    
    def test_create_sms_template(self, client, super_admin_user, db):
        """测试创建短信模板"""
        template_data = {
            "name": "login_code",
            "type": "sms",
            "content": "【{{app_name}}】您的登录验证码是{{code}}，5分钟内有效。",
            "variables": {
                "app_name": "应用名称",
                "code": "验证码"
            }
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "login_code"
        assert data["type"] == "sms"
        assert data["subject"] is None
        assert data["content"] == template_data["content"]
        
        # 验证数据库中已创建
        template = db.query(MessageTemplate).filter(
            MessageTemplate.name == "login_code"
        ).first()
        assert template is not None
        assert template.type == "sms"
    
    def test_create_template_duplicate_name(self, client, super_admin_user, db):
        """测试创建重复名称的模板"""
        # 先创建一个模板
        template = MessageTemplate(
            name="test_template",
            type="email",
            subject="测试",
            content="测试内容"
        )
        db.add(template)
        db.commit()
        
        # 尝试创建同名模板
        template_data = {
            "name": "test_template",
            "type": "sms",
            "content": "另一个测试内容"
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 409
        assert "已存在" in response.json()["detail"]
    
    def test_create_email_template_without_subject(self, client, super_admin_user):
        """测试创建邮件模板但不提供主题"""
        template_data = {
            "name": "no_subject_email",
            "type": "email",
            "content": "测试内容"
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 400
        assert "必须提供主题" in response.json()["detail"]
    
    def test_create_sms_template_with_subject(self, client, super_admin_user):
        """测试创建短信模板但提供了主题"""
        template_data = {
            "name": "sms_with_subject",
            "type": "sms",
            "subject": "不应该有主题",
            "content": "测试内容"
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 400
        assert "不应该包含主题" in response.json()["detail"]
    
    def test_create_template_invalid_type(self, client, super_admin_user):
        """测试创建无效类型的模板"""
        template_data = {
            "name": "invalid_type",
            "type": "invalid",
            "content": "测试内容"
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 400
        assert "无效的模板类型" in response.json()["detail"]
    
    def test_create_template_invalid_jinja2_syntax(self, client, super_admin_user):
        """测试创建包含无效Jinja2语法的模板"""
        template_data = {
            "name": "invalid_syntax",
            "type": "email",
            "subject": "测试",
            "content": "{{unclosed_variable"
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 422
        assert "模板语法错误" in response.json()["detail"]
    
    def test_create_template_requires_super_admin(self, client, regular_user):
        """测试非超级管理员无法创建模板"""
        template_data = {
            "name": "test",
            "type": "email",
            "subject": "测试",
            "content": "测试内容"
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(regular_user.id)}
        )
        
        assert response.status_code == 403


class TestMessageTemplateGet:
    """测试获取单个消息模板"""
    
    def test_get_template(self, client, super_admin_user, db):
        """测试获取模板详情"""
        template = MessageTemplate(
            name="test_template",
            type="email",
            subject="测试主题",
            content="测试内容 {{variable}}",
            variables={"variable": "变量说明"}
        )
        db.add(template)
        db.commit()
        
        response = client.get(
            f"/api/v1/admin/templates/{template.id}",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(template.id)
        assert data["name"] == "test_template"
        assert data["type"] == "email"
        assert data["subject"] == "测试主题"
        assert data["content"] == "测试内容 {{variable}}"
        assert data["variables"] == {"variable": "变量说明"}
    
    def test_get_template_not_found(self, client, super_admin_user):
        """测试获取不存在的模板"""
        fake_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/admin/templates/{fake_id}",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 404
        assert "不存在" in response.json()["detail"]
    
    def test_get_template_invalid_id(self, client, super_admin_user):
        """测试使用无效ID获取模板"""
        response = client.get(
            "/api/v1/admin/templates/invalid-id",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 422
        assert "无效的模板ID" in response.json()["detail"]


class TestMessageTemplateUpdate:
    """测试消息模板更新"""
    
    def test_update_template_content(self, client, super_admin_user, db):
        """测试更新模板内容"""
        template = MessageTemplate(
            name="test_template",
            type="email",
            subject="原始主题",
            content="原始内容"
        )
        db.add(template)
        db.commit()
        
        update_data = {
            "content": "更新后的内容 {{new_variable}}"
        }
        
        response = client.put(
            f"/api/v1/admin/templates/{template.id}",
            json=update_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "更新后的内容 {{new_variable}}"
        assert data["subject"] == "原始主题"  # 未更新的字段保持不变
        
        # 验证数据库已更新
        db.refresh(template)
        assert template.content == "更新后的内容 {{new_variable}}"
    
    def test_update_template_subject(self, client, super_admin_user, db):
        """测试更新邮件模板主题"""
        template = MessageTemplate(
            name="test_template",
            type="email",
            subject="原始主题",
            content="原始内容"
        )
        db.add(template)
        db.commit()
        
        update_data = {
            "subject": "更新后的主题 {{variable}}"
        }
        
        response = client.put(
            f"/api/v1/admin/templates/{template.id}",
            json=update_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["subject"] == "更新后的主题 {{variable}}"
        
        # 验证数据库已更新
        db.refresh(template)
        assert template.subject == "更新后的主题 {{variable}}"
    
    def test_update_template_variables(self, client, super_admin_user, db):
        """测试更新模板变量说明"""
        template = MessageTemplate(
            name="test_template",
            type="email",
            subject="主题",
            content="内容",
            variables={"old_var": "旧变量"}
        )
        db.add(template)
        db.commit()
        
        update_data = {
            "variables": {
                "new_var1": "新变量1",
                "new_var2": "新变量2"
            }
        }
        
        response = client.put(
            f"/api/v1/admin/templates/{template.id}",
            json=update_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["variables"] == {"new_var1": "新变量1", "new_var2": "新变量2"}
        
        # 验证数据库已更新
        db.refresh(template)
        assert template.variables == {"new_var1": "新变量1", "new_var2": "新变量2"}
    
    def test_update_email_template_remove_subject(self, client, super_admin_user, db):
        """测试尝试移除邮件模板的主题"""
        template = MessageTemplate(
            name="test_template",
            type="email",
            subject="原始主题",
            content="原始内容"
        )
        db.add(template)
        db.commit()
        
        update_data = {
            "subject": ""
        }
        
        response = client.put(
            f"/api/v1/admin/templates/{template.id}",
            json=update_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 400
        assert "必须提供主题" in response.json()["detail"]
    
    def test_update_sms_template_add_subject(self, client, super_admin_user, db):
        """测试尝试为短信模板添加主题"""
        template = MessageTemplate(
            name="test_template",
            type="sms",
            content="原始内容"
        )
        db.add(template)
        db.commit()
        
        update_data = {
            "subject": "不应该有主题"
        }
        
        response = client.put(
            f"/api/v1/admin/templates/{template.id}",
            json=update_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 400
        assert "不应该包含主题" in response.json()["detail"]
    
    def test_update_template_invalid_syntax(self, client, super_admin_user, db):
        """测试更新为无效的Jinja2语法"""
        template = MessageTemplate(
            name="test_template",
            type="email",
            subject="主题",
            content="原始内容"
        )
        db.add(template)
        db.commit()
        
        update_data = {
            "content": "{{invalid syntax"
        }
        
        response = client.put(
            f"/api/v1/admin/templates/{template.id}",
            json=update_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 422
        assert "模板语法错误" in response.json()["detail"]
    
    def test_update_template_not_found(self, client, super_admin_user):
        """测试更新不存在的模板"""
        fake_id = str(uuid.uuid4())
        update_data = {
            "content": "新内容"
        }
        
        response = client.put(
            f"/api/v1/admin/templates/{fake_id}",
            json=update_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 404
        assert "不存在" in response.json()["detail"]


class TestMessageTemplateDelete:
    """测试消息模板删除"""
    
    def test_delete_template(self, client, super_admin_user, db):
        """测试删除模板"""
        template = MessageTemplate(
            name="test_template",
            type="email",
            subject="测试",
            content="测试内容"
        )
        db.add(template)
        db.commit()
        template_id = template.id
        
        response = client.delete(
            f"/api/v1/admin/templates/{template_id}",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "已删除" in data["message"]
        
        # 验证数据库中已删除
        deleted_template = db.query(MessageTemplate).filter(
            MessageTemplate.id == template_id
        ).first()
        assert deleted_template is None
    
    def test_delete_template_not_found(self, client, super_admin_user):
        """测试删除不存在的模板"""
        fake_id = str(uuid.uuid4())
        response = client.delete(
            f"/api/v1/admin/templates/{fake_id}",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 404
        assert "不存在" in response.json()["detail"]
    
    def test_delete_template_invalid_id(self, client, super_admin_user):
        """测试使用无效ID删除模板"""
        response = client.delete(
            "/api/v1/admin/templates/invalid-id",
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 422
        assert "无效的模板ID" in response.json()["detail"]


class TestTemplateVariableReplacement:
    """测试模板变量替换逻辑"""
    
    def test_template_with_simple_variables(self, client, super_admin_user, db):
        """测试简单变量替换"""
        template_data = {
            "name": "simple_vars",
            "type": "email",
            "subject": "Hello {{name}}",
            "content": "Welcome {{name}}, your code is {{code}}.",
            "variables": {
                "name": "用户名",
                "code": "验证码"
            }
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 201
        
        # 验证模板可以被正确渲染（通过email_service）
        from jinja2 import Template
        template = Template(template_data["content"])
        rendered = template.render(name="John", code="123456")
        assert rendered == "Welcome John, your code is 123456."
    
    def test_template_with_nested_variables(self, client, super_admin_user, db):
        """测试嵌套变量"""
        template_data = {
            "name": "nested_vars",
            "type": "email",
            "subject": "Order {{order.id}}",
            "content": "Dear {{user.name}}, your order {{order.id}} is {{order.status}}.",
            "variables": {
                "user.name": "用户名",
                "order.id": "订单ID",
                "order.status": "订单状态"
            }
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 201
        
        # 验证模板可以被正确渲染
        from jinja2 import Template
        template = Template(template_data["content"])
        rendered = template.render(
            user={"name": "John"},
            order={"id": "12345", "status": "shipped"}
        )
        assert "John" in rendered
        assert "12345" in rendered
        assert "shipped" in rendered
    
    def test_template_with_filters(self, client, super_admin_user, db):
        """测试Jinja2过滤器"""
        template_data = {
            "name": "with_filters",
            "type": "email",
            "subject": "{{title|upper}}",
            "content": "Hello {{name|title}}, today is {{date|default('unknown')}}.",
            "variables": {
                "title": "标题",
                "name": "姓名",
                "date": "日期"
            }
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 201
        
        # 验证模板可以被正确渲染
        from jinja2 import Template
        template = Template(template_data["content"])
        rendered = template.render(name="john doe")
        assert "John Doe" in rendered
        assert "unknown" in rendered
    
    def test_template_with_conditionals(self, client, super_admin_user, db):
        """测试条件语句"""
        template_data = {
            "name": "with_conditionals",
            "type": "email",
            "subject": "Notification",
            "content": "{% if is_premium %}Premium user{% else %}Regular user{% endif %}: {{name}}",
            "variables": {
                "is_premium": "是否为高级用户",
                "name": "用户名"
            }
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 201
        
        # 验证模板可以被正确渲染
        from jinja2 import Template
        template = Template(template_data["content"])
        
        rendered_premium = template.render(is_premium=True, name="John")
        assert "Premium user: John" in rendered_premium
        
        rendered_regular = template.render(is_premium=False, name="Jane")
        assert "Regular user: Jane" in rendered_regular
    
    def test_template_with_loops(self, client, super_admin_user, db):
        """测试循环语句"""
        template_data = {
            "name": "with_loops",
            "type": "email",
            "subject": "Your items",
            "content": "Items: {% for item in items %}{{item}}{% if not loop.last %}, {% endif %}{% endfor %}",
            "variables": {
                "items": "物品列表"
            }
        }
        
        response = client.post(
            "/api/v1/admin/templates",
            json=template_data,
            params={"user_id": str(super_admin_user.id)}
        )
        
        assert response.status_code == 201
        
        # 验证模板可以被正确渲染
        from jinja2 import Template
        template = Template(template_data["content"])
        rendered = template.render(items=["apple", "banana", "orange"])
        assert "Items: apple, banana, orange" in rendered


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
