# 实施计划：用户自动配置（User Auto-Provisioning）

## 任务 1: 数据模型与数据库迁移

- [x] 1.1 在 `shared/models/application.py` 中新增 `AutoProvisionConfig` 模型，包含 `id`、`application_id`（unique）、`role_ids`（JSONB）、`permission_ids`（JSONB）、`organization_id`、`subscription_plan_id`、`is_enabled`、`created_at`、`updated_at` 字段
- [x] 1.2 在 `Application` 模型中新增 `auto_provision_config` 关系（one-to-one, cascade delete-orphan, uselist=False）
- [x] 1.3 创建 Alembic 迁移文件 `alembic/versions/006_add_auto_provision_config.py`，创建 `auto_provision_configs` 表

## 任务 2: Admin Service API 端点

- [x] 2.1 在 `services/admin/main.py` 中新增 Pydantic 模型 `AutoProvisionConfigUpdate` 和 `AutoProvisionConfigResponse`
- [x] 2.2 实现 `GET /api/v1/admin/applications/{app_id}/auto-provision` 端点，返回配置数据（不存在时返回默认空配置）
- [x] 2.3 实现 `PUT /api/v1/admin/applications/{app_id}/auto-provision` 端点，包含 role_ids/permission_ids/organization_id/subscription_plan_id 的有效性校验，校验失败返回 400
- [x] 2.4 实现 `DELETE /api/v1/admin/applications/{app_id}/auto-provision` 端点
- [x] 2.5 所有端点添加 `require_super_admin` 权限校验

## 任务 3: Admin API 单元测试

- [x] 3.1 创建 `tests/test_admin_auto_provision.py`，编写 GET/PUT/DELETE 正常流程测试
- [x] 3.2 编写无效 role_ids/permission_ids/organization_id/subscription_plan_id 的 400 错误测试
- [x] 3.3 编写非超级管理员访问返回 403 的测试
- [x] 3.4 编写应用不存在时返回 404 的测试

## 任务 4: Admin API 属性测试

- [x] 4.1 创建 `tests/test_auto_provision_properties.py`，实现 Property 1（配置读写往返一致性）属性测试
- [x] 4.2 实现 Property 2（无效引用 ID 校验）属性测试
- [x] 4.3 实现 Property 3（应用删除级联清除配置）属性测试
- [x] 4.4 实现 Property 4（一对一唯一约束）属性测试
- [x] 4.5 实现 Property 9（超级管理员权限控制）属性测试

## 任务 5: Gateway 自动配置执行器

- [x] 5.1 在 `services/gateway/main.py` 中实现 `_apply_auto_provision(app_data, user_id)` 函数，包含查询配置、幂等角色分配、幂等权限分配、幂等组织加入、幂等订阅创建，每步独立 try/except
- [x] 5.2 在 `gateway_register_email` 中，`_create_app_user_binding` 之后调用 `_apply_auto_provision`
- [x] 5.3 在 `gateway_register_phone` 中，`_create_app_user_binding` 之后调用 `_apply_auto_provision`
- [x] 5.4 在 `gateway_oauth` 中，`is_new_user=True` 且 `_create_app_user_binding` 之后调用 `_apply_auto_provision`

## 任务 6: Gateway 单元测试

- [x] 6.1 创建 `tests/test_gateway_auto_provision.py`，编写邮箱注册触发自动配置的测试
- [x] 6.2 编写手机注册触发自动配置的测试
- [x] 6.3 编写 OAuth 首次注册触发自动配置的测试
- [x] 6.4 编写配置禁用时不触发自动配置的测试
- [x] 6.5 编写部分失败容错的测试（模拟某步骤异常，验证其余步骤仍执行）

## 任务 7: Gateway 属性测试

- [x] 7.1 在 `tests/test_auto_provision_properties.py` 中实现 Property 5（注册自动配置执行）属性测试
- [x] 7.2 实现 Property 6（禁用配置不触发）属性测试
- [x] 7.3 实现 Property 7（自动配置幂等性）属性测试
- [x] 7.4 实现 Property 8（部分失败容错）属性测试
- [x] 7.5 实现 Property 10（删除配置后不再生效）属性测试

## 任务 8: 前端 API 扩展

- [x] 8.1 在 `admin-ui/src/api/services.ts` 的 `applicationApi` 中新增 `getAutoProvision`、`updateAutoProvision`、`deleteAutoProvision` 方法

## 任务 9: 前端自动配置卡片

- [x] 9.1 在 `ApplicationDetail.tsx` 中新增状态变量：autoProvisionEnabled、selectedRoleIds、selectedPermissionIds、selectedOrgId、selectedAutoProvisionPlanId、savingAutoProvision
- [x] 9.2 新增 `fetchAutoProvision` 数据加载函数，在组件初始化时调用
- [x] 9.3 新增 `fetchRoles` 和 `fetchPermissions` 函数，加载系统角色和权限列表供选择
- [x] 9.4 在"订阅计划配置"卡片之后、"危险操作"卡片之前，新增"用户自动配置"卡片，包含总开关（Switch）、角色多选（Select）、权限多选（Select）、组织树选择（TreeSelect）、订阅计划单选（Radio.Group）、保存按钮
- [x] 9.5 实现 `saveAutoProvision` 函数，调用 PUT API 保存配置，成功显示成功提示，失败显示错误信息
