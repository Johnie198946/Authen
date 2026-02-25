# 需求文档：用户自动配置（User Auto-Provisioning）

## 简介

在应用管理中新增"用户自动配置"功能节点。当第三方系统通过 API 网关注册用户时，系统根据该应用预先配置的自动配置规则，自动为新注册用户分配角色、权限、组织归属和订阅计划。每个应用可独立配置不同的自动配置规则。

## 术语表

- **Auto_Provision_Config（自动配置规则）**: 与 Application 关联的配置记录，定义新注册用户应自动获得的角色、权限、组织和订阅计划
- **Application（应用）**: 已注册到统一认证平台的第三方应用，由 `applications` 表管理
- **Admin_Service（管理服务）**: 运行在端口 8007 的后端微服务，提供应用管理 API
- **Gateway（网关）**: 运行在端口 8008 的 API 网关，第三方系统通过网关注册用户
- **Admin_UI（管理界面）**: 基于 React + Ant Design 的管理后台前端
- **ApplicationDetail（应用详情页）**: Admin_UI 中展示和管理单个应用配置的页面组件
- **Role（角色）**: 系统中的角色实体，存储在 `roles` 表中
- **Permission（权限）**: 系统中的权限实体，存储在 `permissions` 表中
- **Organization（组织）**: 系统中的组织架构节点，存储在 `organizations` 表中
- **Subscription_Plan（订阅计划）**: 系统中的订阅计划实体，存储在 `subscription_plans` 表中

## 需求

### 需求 1：自动配置规则数据模型

**用户故事：** 作为平台管理员，我希望每个应用都能存储一套用户自动配置规则，以便新注册用户能自动获得预设的角色、权限、组织和订阅。

#### 验收标准

1. THE Auto_Provision_Config SHALL 与 Application 保持一对一关系，通过 `application_id` 外键关联
2. THE Auto_Provision_Config SHALL 包含以下字段：`role_ids`（角色 ID 列表）、`permission_ids`（权限 ID 列表）、`organization_id`（组织 ID，单选）、`subscription_plan_id`（订阅计划 ID，单选）、`is_enabled`（是否启用）
3. WHEN Application 被删除时，THE Auto_Provision_Config SHALL 通过级联删除自动清除关联的配置记录
4. THE Auto_Provision_Config 中的 `role_ids`、`permission_ids`、`organization_id`、`subscription_plan_id` SHALL 均为可选字段，允许部分配置

### 需求 2：自动配置规则管理 API

**用户故事：** 作为平台管理员，我希望通过 API 对应用的自动配置规则进行增删改查，以便灵活管理每个应用的用户初始化策略。

#### 验收标准

1. THE Admin_Service SHALL 提供 `GET /api/v1/admin/applications/{app_id}/auto-provision` 端点，返回指定应用的自动配置规则
2. THE Admin_Service SHALL 提供 `PUT /api/v1/admin/applications/{app_id}/auto-provision` 端点，创建或更新指定应用的自动配置规则
3. THE Admin_Service SHALL 提供 `DELETE /api/v1/admin/applications/{app_id}/auto-provision` 端点，删除指定应用的自动配置规则
4. WHEN 请求中的 `role_ids` 包含不存在的角色 ID 时，THE Admin_Service SHALL 返回 400 错误并说明无效的角色 ID
5. WHEN 请求中的 `permission_ids` 包含不存在的权限 ID 时，THE Admin_Service SHALL 返回 400 错误并说明无效的权限 ID
6. WHEN 请求中的 `organization_id` 指向不存在的组织时，THE Admin_Service SHALL 返回 400 错误并说明无效的组织 ID
7. WHEN 请求中的 `subscription_plan_id` 指向不存在的订阅计划时，THE Admin_Service SHALL 返回 400 错误并说明无效的订阅计划 ID
8. THE Admin_Service 的自动配置规则管理端点 SHALL 仅允许超级管理员访问

### 需求 3：网关注册时自动应用配置规则

**用户故事：** 作为第三方应用开发者，我希望通过网关注册的用户能自动获得该应用预配置的角色、权限、组织和订阅，以便用户注册后即可使用应用功能。

#### 验收标准

1. WHEN 用户通过 Gateway 的邮箱注册端点成功注册，且该应用存在已启用的 Auto_Provision_Config 时，THE Gateway SHALL 自动为该用户分配配置中指定的角色
2. WHEN 用户通过 Gateway 的手机注册端点成功注册，且该应用存在已启用的 Auto_Provision_Config 时，THE Gateway SHALL 自动为该用户分配配置中指定的角色
3. WHEN Auto_Provision_Config 中配置了 `permission_ids` 时，THE Gateway SHALL 通过调用 Permission_Service 为新注册用户分配指定的权限
4. WHEN Auto_Provision_Config 中配置了 `organization_id` 时，THE Gateway SHALL 通过调用 Organization_Service 将新注册用户加入指定的组织
5. WHEN Auto_Provision_Config 中配置了 `subscription_plan_id` 时，THE Gateway SHALL 通过调用 Subscription_Service 为新注册用户创建订阅记录
6. WHEN 用户通过 Gateway 的 OAuth 登录端点首次注册（`is_new_user` 为 true）时，THE Gateway SHALL 同样应用 Auto_Provision_Config 中的配置规则
7. IF 自动配置过程中某一项分配失败（如角色分配失败），THEN THE Gateway SHALL 记录错误日志但继续执行其余分配操作，用户注册本身不受影响
8. WHILE Auto_Provision_Config 的 `is_enabled` 字段为 false 时，THE Gateway SHALL 跳过自动配置流程，仅执行原有的 AppUser 绑定逻辑

### 需求 4：管理界面配置面板

**用户故事：** 作为平台管理员，我希望在应用详情页中通过可视化界面配置用户自动配置规则，以便直观地管理每个应用的用户初始化策略。

#### 验收标准

1. THE ApplicationDetail SHALL 在现有配置卡片之后新增一个"用户自动配置"卡片
2. THE "用户自动配置"卡片 SHALL 包含一个总开关，用于启用或禁用该应用的自动配置功能
3. THE "用户自动配置"卡片 SHALL 提供角色多选组件，展示系统中所有可用角色供管理员勾选
4. THE "用户自动配置"卡片 SHALL 提供权限多选组件，展示系统中所有可用权限供管理员勾选
5. THE "用户自动配置"卡片 SHALL 提供组织选择组件，以树形结构展示组织架构供管理员选择一个目标组织
6. THE "用户自动配置"卡片 SHALL 提供订阅计划单选组件，展示所有可用订阅计划供管理员选择
7. WHEN 管理员点击保存按钮时，THE Admin_UI SHALL 调用 `PUT /api/v1/admin/applications/{app_id}/auto-provision` 端点保存配置
8. WHEN 保存成功时，THE Admin_UI SHALL 显示成功提示消息
9. IF 保存失败，THEN THE Admin_UI SHALL 显示具体的错误信息

### 需求 5：自动配置的幂等性与一致性

**用户故事：** 作为平台管理员，我希望自动配置过程是幂等的，以便重复触发不会产生重复数据。

#### 验收标准

1. WHEN 为用户分配角色时，THE Gateway SHALL 检查用户是否已拥有该角色，已存在的角色分配记录不重复创建
2. WHEN 为用户分配权限时，THE Gateway SHALL 检查用户是否已拥有该权限，已存在的权限分配记录不重复创建
3. WHEN 将用户加入组织时，THE Gateway SHALL 检查用户是否已属于该组织，已存在的组织关联记录不重复创建
4. WHEN 为用户创建订阅时，THE Gateway SHALL 检查用户是否已有该计划的有效订阅，已存在有效订阅时不重复创建
