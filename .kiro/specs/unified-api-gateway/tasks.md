# 实现计划：统一 API 网关

## 概述

基于现有微服务架构，新增 Gateway Service（端口 8008）作为三方系统对接入口，在 Admin Panel 中新增应用管理页面。后端使用 Python FastAPI，前端使用 TypeScript React + Ant Design。实现按数据模型 → 后端核心组件 → 网关端点 → Admin API → 前端页面的顺序递进，每个阶段包含属性测试验证。

## 任务

- [x] 1. 数据模型与数据库迁移
  - [x] 1.1 创建 Application 相关 SQLAlchemy 模型
    - 新建 `shared/models/application.py`，定义 Application、AppLoginMethod、AppScope、AppUser 四个模型
    - 包含所有字段、约束、关系和联合唯一索引
    - 在 `shared/models/__init__.py` 中导出新模型
    - _需求: 1.1, 2.1, 5.1, 3.8_

  - [x] 1.2 创建 Alembic 数据库迁移
    - 新建 `alembic/versions/XXX_add_application_tables.py`
    - 创建 applications、app_login_methods、app_scopes、app_users 四张表
    - 包含所有索引和外键约束
    - _需求: 1.1_

  - [ ]* 1.3 编写属性测试：凭证创建与哈希验证往返
    - **Property 1: 应用凭证创建与哈希验证往返**
    - 测试文件: `tests/test_gateway_credential_properties.py`
    - 验证 app_id 为合法 UUID，app_secret >= 32 字节，verify_password 返回 True
    - **验证: 需求 1.1, 1.2**

  - [ ]* 1.4 编写属性测试：重置凭证使旧凭证失效
    - **Property 2: 重置凭证使旧凭证失效**
    - 测试文件: `tests/test_gateway_credential_properties.py`
    - 验证旧 app_secret 失效，新 app_secret 有效
    - **验证: 需求 1.3**

- [x] 2. 网关核心组件
  - [x] 2.1 实现应用凭证验证模块
    - 新建 `services/gateway/__init__.py` 和 `services/gateway/dependencies.py`
    - 实现 `verify_app_credential(app_id, app_secret)` 函数
    - 从 Redis 缓存或数据库加载应用配置
    - 凭证验证失败统一返回 401，应用禁用返回 403
    - 复用 `shared/utils/crypto.verify_password`
    - _需求: 3.6, 1.4, 4.1, 4.2_

  - [x] 2.2 实现 Redis 缓存管理模块
    - 新建 `services/gateway/cache.py`
    - 实现应用配置缓存读写（app:{app_id}、app:{app_id}:methods、app:{app_id}:scopes）
    - TTL 300 秒，配置变更时删除对应 key
    - 复用 `shared/redis_client`
    - _需求: 2.4, 5.3_

  - [ ]* 2.3 编写属性测试：配置变更使缓存失效
    - **Property 7: 配置变更使缓存失效**
    - 测试文件: `tests/test_gateway_cache_properties.py`
    - 验证配置变更后 Redis 缓存 key 被删除
    - **验证: 需求 2.4, 5.3**

  - [ ]* 2.4 编写属性测试：删除应用清除 Redis 缓存
    - **Property 4: 删除应用清除 Redis 缓存**
    - 测试文件: `tests/test_gateway_cache_properties.py`
    - 验证删除应用后所有 app:{app_id} 前缀 key 不存在
    - **验证: 需求 1.6**

  - [x] 2.5 实现 Scope 权限检查模块
    - 新建 `services/gateway/scope_checker.py`
    - 定义 ENDPOINT_SCOPE_MAP 映射表
    - 实现 `check_scope(app_id, endpoint)` 函数，从缓存加载 Scope 列表并验证
    - 缺少 Scope 返回 403 + insufficient_scope
    - _需求: 5.2, 5.4_

  - [ ]* 2.6 编写属性测试：缺少 Scope 的请求被拒绝
    - **Property 14: 缺少 Scope 的请求被拒绝**
    - 测试文件: `tests/test_gateway_access_control_properties.py`
    - 验证未授权 Scope 返回 403 + insufficient_scope
    - **验证: 需求 5.2, 5.4**

  - [x] 2.7 实现限流器模块
    - 新建 `services/gateway/rate_limiter.py`
    - 使用 Redis ZSET 实现滑动窗口算法，按 app_id 维度限流
    - 返回 X-RateLimit-Limit、X-RateLimit-Remaining、X-RateLimit-Reset 响应头
    - 超限返回 429 + Retry-After
    - _需求: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 2.8 编写属性测试：滑动窗口限流
    - **Property 15: 滑动窗口限流**
    - 测试文件: `tests/test_gateway_ratelimit_properties.py`
    - 验证超过阈值后返回 429 + Retry-After
    - **验证: 需求 6.1, 6.3**

  - [ ]* 2.9 编写属性测试：所有响应包含限流头
    - **Property 16: 所有响应包含限流头**
    - 测试文件: `tests/test_gateway_ratelimit_properties.py`
    - 验证响应头包含三个限流字段且 Remaining <= Limit
    - **验证: 需求 6.4**

  - [x] 2.10 实现内部服务路由器
    - 新建 `services/gateway/router.py`
    - 实现 ServiceRouter 类，封装 httpx.AsyncClient 调用下游微服务
    - 统一超时处理（10 秒），下游不可用返回 503
    - _需求: 8.2, 9.2, 9.4_

  - [x] 2.11 实现统一错误处理与 request_id 生成
    - 新建 `services/gateway/error_handler.py`
    - 统一错误响应格式：{error_code, message, request_id}
    - 每个请求生成唯一 UUID request_id，通过 X-Request-Id 响应头返回
    - 隐藏下游微服务实现细节
    - _需求: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 2.12 编写属性测试：统一错误响应格式
    - **Property 20: 统一错误响应格式**
    - 测试文件: `tests/test_gateway_response_properties.py`
    - 验证错误响应仅包含 error_code、message、request_id 三个字段
    - **验证: 需求 9.1, 9.2**

  - [ ]* 2.13 编写属性测试：每个请求有唯一 request_id
    - **Property 21: 每个请求有唯一 request_id**
    - 测试文件: `tests/test_gateway_response_properties.py`
    - 验证 X-Request-Id 为合法 UUID 且不同请求互不相同
    - **验证: 需求 9.3**

- [x] 3. 检查点 - 核心组件验证
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 4. 网关 API 端点实现
  - [x] 4.1 创建 Gateway Service 主应用
    - 新建 `services/gateway/main.py`，创建 FastAPI 应用（端口 8008）
    - 注册中间件：request_id 生成、限流头注入、审计日志
    - 复用 `shared/utils/health_check` 实现 /health 端点
    - 实现 /api/v1/gateway/info 端点
    - _需求: 8.1, 8.3, 8.4_

  - [x] 4.2 实现认证类 API 端点
    - 在 `services/gateway/main.py` 中实现：
      - POST /api/v1/gateway/auth/register/email（路由到 Auth :8001）
      - POST /api/v1/gateway/auth/register/phone（路由到 Auth :8001）
      - POST /api/v1/gateway/auth/login（路由到 Auth :8001）
      - POST /api/v1/gateway/auth/oauth/{provider}（路由到 Auth :8001，使用应用级 OAuth 配置）
      - POST /api/v1/gateway/auth/refresh（路由到 Auth :8001）
    - 每个端点执行：凭证验证 → 登录方式检查 → Scope 检查 → 限流 → 路由 → 审计日志
    - 注册成功后创建 AppUser 绑定记录
    - Token payload 注入 app_id
    - _需求: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 3.8, 4.6_

  - [ ]* 4.3 编写属性测试：凭证验证失败返回统一错误
    - **Property 11: 凭证验证失败返回统一错误**
    - 测试文件: `tests/test_gateway_credential_properties.py`
    - 验证无效凭证组合返回相同 401 响应体
    - **验证: 需求 3.6**

  - [ ]* 4.4 编写属性测试：禁用应用拒绝所有请求
    - **Property 3: 禁用应用拒绝所有请求**
    - 测试文件: `tests/test_gateway_access_control_properties.py`
    - 验证 disabled 应用返回 403
    - **验证: 需求 1.4**

  - [ ]* 4.5 编写属性测试：禁用的登录方式拒绝请求
    - **Property 6: 禁用的登录方式拒绝请求**
    - 测试文件: `tests/test_gateway_access_control_properties.py`
    - 验证禁用登录方式返回 400 + 已启用方式列表
    - **验证: 需求 2.3, 3.7**

  - [ ]* 4.6 编写属性测试：网关路由认证请求到正确的下游服务
    - **Property 9: 网关路由认证请求到正确的下游服务**
    - 测试文件: `tests/test_gateway_routing_properties.py`
    - 验证注册/登录请求被正确路由到 Auth Service
    - **验证: 需求 3.1, 3.2, 3.3, 3.5**

  - [ ]* 4.7 编写属性测试：OAuth 登录使用应用级配置
    - **Property 10: OAuth 登录使用应用级配置**
    - 测试文件: `tests/test_gateway_routing_properties.py`
    - 验证 OAuth 请求使用应用自身的 client_id/client_secret
    - **验证: 需求 3.4**

  - [ ]* 4.8 编写属性测试：注册成功创建应用用户绑定
    - **Property 12: 注册成功创建应用用户绑定**
    - 测试文件: `tests/test_gateway_routing_properties.py`
    - 验证注册后 AppUser 表存在绑定记录
    - **验证: 需求 3.8**

  - [ ]* 4.9 编写属性测试：Token 包含 app_id 且跨应用不可用
    - **Property 13: Token 包含 app_id 且跨应用不可用**
    - 测试文件: `tests/test_gateway_routing_properties.py`
    - 验证 Token payload 包含 app_id，跨应用使用被拒绝
    - **验证: 需求 4.3, 4.6**

  - [x] 4.10 实现用户管理类 API 端点
    - 在 `services/gateway/main.py` 中实现：
      - GET /api/v1/gateway/users/{user_id}（路由到 User :8003）
      - GET /api/v1/gateway/users/{user_id}/roles（路由到 Permission :8004）
      - POST /api/v1/gateway/users/{user_id}/permissions/check（路由到 Permission :8004）
      - POST /api/v1/gateway/auth/change-password（路由到 Auth :8001）
    - Bearer Token 鉴权：解析 Token、验证 app_id 归属、检查 AppUser 绑定
    - 复用 `shared/utils/jwt` 解析 Token
    - _需求: 7.1, 7.2, 7.3, 7.4, 7.5, 4.3, 4.4, 4.5_

  - [ ]* 4.11 编写属性测试：非绑定用户访问被拒绝
    - **Property 18: 非绑定用户访问被拒绝**
    - 测试文件: `tests/test_gateway_access_control_properties.py`
    - 验证非 AppUser 用户返回 403 + user_not_bound
    - **验证: 需求 7.5**

  - [ ]* 4.12 编写属性测试：下游服务不可用返回 503
    - **Property 19: 下游服务不可用返回 503**
    - 测试文件: `tests/test_gateway_response_properties.py`（或 `test_gateway_health.py`）
    - 验证下游不可用时返回 503
    - **验证: 需求 8.2**

  - [ ]* 4.13 编写属性测试：审计日志记录完整
    - **Property 17: 审计日志记录完整**
    - 测试文件: `tests/test_gateway_response_properties.py`
    - 验证审计日志包含 app_id、路径、方法、状态码、响应时间
    - **验证: 需求 6.5**

  - [ ]* 4.14 编写单元测试：边界情况
    - 测试文件: `tests/test_gateway_edge_cases.py`
    - 测试过期 Token 返回 token_expired（需求 4.4）
    - 测试无效 Token 返回 invalid_token（需求 4.5）
    - 测试下游非预期错误格式返回 502 upstream_error（需求 9.4）
    - _需求: 4.4, 4.5, 9.4_

  - [ ]* 4.15 编写单元测试：健康检查与网关信息
    - 测试文件: `tests/test_gateway_health.py`
    - 测试 /health 端点返回所有下游服务状态（需求 8.1）
    - 测试 /api/v1/gateway/info 端点返回版本和登录方式列表（需求 8.4）
    - 测试降级启动模式（需求 8.3）
    - _需求: 8.1, 8.3, 8.4_

- [x] 5. 检查点 - 网关 API 验证
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 6. Admin Service 应用管理 API
  - [x] 6.1 实现应用 CRUD API
    - 在 `services/admin/main.py` 中新增应用管理端点：
      - POST /api/v1/admin/applications（创建应用，生成 app_id + app_secret）
      - GET /api/v1/admin/applications（应用列表）
      - GET /api/v1/admin/applications/{app_id}（应用详情）
      - PUT /api/v1/admin/applications/{app_id}（更新应用）
      - DELETE /api/v1/admin/applications/{app_id}（删除应用，清除 Redis 缓存）
      - POST /api/v1/admin/applications/{app_id}/reset-secret（重置 app_secret）
      - PUT /api/v1/admin/applications/{app_id}/status（启用/禁用应用）
    - _需求: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 6.2 实现登录方式配置 API
    - 在 `services/admin/main.py` 中新增：
      - GET /api/v1/admin/applications/{app_id}/login-methods（获取登录方式列表）
      - PUT /api/v1/admin/applications/{app_id}/login-methods（更新登录方式配置）
    - OAuth 类型启用时校验 client_id 和 client_secret 必填
    - 使用 `shared/utils/crypto.encrypt_config` 加密存储 OAuth 配置
    - 配置变更后清除 Redis 缓存
    - _需求: 2.1, 2.2, 2.4, 2.5_

  - [ ]* 6.3 编写属性测试：OAuth 登录方式启用需要完整配置
    - **Property 5: OAuth 登录方式启用需要完整配置**
    - 测试文件: `tests/test_gateway_access_control_properties.py`
    - 验证 OAuth 启用时缺少 client_id/client_secret 被拒绝
    - **验证: 需求 2.2**

  - [ ]* 6.4 编写属性测试：OAuth client_secret 加密存储往返
    - **Property 8: OAuth client_secret 加密存储往返**
    - 测试文件: `tests/test_gateway_crypto_properties.py`
    - 验证加密后解密得到原始值，API 返回仅展示末尾 4 位
    - **验证: 需求 2.5**

  - [x] 6.5 实现 Scope 配置 API
    - 在 `services/admin/main.py` 中新增：
      - GET /api/v1/admin/applications/{app_id}/scopes（获取 Scope 列表）
      - PUT /api/v1/admin/applications/{app_id}/scopes（更新 Scope 配置）
    - 配置变更后清除 Redis 缓存
    - _需求: 5.1, 5.3_

- [x] 7. 检查点 - Admin API 验证
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 8. Admin Panel 前端应用管理页面
  - [x] 8.1 新增应用管理 API 客户端
    - 在 `admin-ui/src/api/services.ts` 中新增应用管理相关 API 调用函数
    - 包含应用 CRUD、登录方式配置、Scope 配置、重置凭证等接口
    - _需求: 1.5_

  - [x] 8.2 实现应用列表页面
    - 新建 `admin-ui/src/pages/panels/ApplicationsPanel.tsx`
    - 展示应用名称、app_id、状态、创建时间
    - 支持创建应用（弹窗显示 app_secret，仅展示一次）
    - 支持禁用/启用、删除应用
    - 遵循现有 Panel 组件模式（参考 UsersPanel.tsx）
    - _需求: 1.1, 1.3, 1.4, 1.5, 1.6_

  - [x] 8.3 实现应用详情页面
    - 新建 `admin-ui/src/pages/panels/ApplicationDetail.tsx`
    - 登录方式配置区域：启用/禁用各登录方式，OAuth 类型填写 client_id/client_secret
    - Scope 权限配置区域：勾选授权的权限范围
    - 限流配置区域：设置每分钟请求限制
    - 重置 app_secret 按钮（二次确认）
    - _需求: 2.1, 2.2, 2.5, 5.1, 6.2_

  - [x] 8.4 集成应用管理页面到 Dashboard
    - 在 `admin-ui/src/pages/Dashboard.tsx` 中新增"应用管理"Tab
    - 在 `admin-ui/src/App.tsx` 中添加路由（如需要）
    - _需求: 1.5_

- [x] 9. 检查点 - 前端页面验证
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 10. 集成与收尾
  - [x] 10.1 更新 docker-compose.yml
    - 新增 gateway 服务配置（端口 8008）
    - 配置环境变量和依赖关系
    - _需求: 8.3_

  - [ ]* 10.2 编写集成测试
    - 测试文件: `tests/test_gateway_integration.py`
    - 测试网关到 Auth Service 的完整注册/登录流程
    - 测试网关到 User/Permission Service 的用户管理流程
    - _需求: 3.1, 3.2, 3.3, 7.1, 7.2, 7.3_

- [x] 11. 最终检查点 - 全部验证
  - 确保所有测试通过，如有问题请向用户确认。

## 备注

- 标记 `*` 的子任务为可选任务，可跳过以加速 MVP 交付
- 每个任务引用了具体的需求编号，确保需求可追溯
- 属性测试使用 Hypothesis 库，每个属性对应设计文档中的一条正确性属性
- 检查点任务用于阶段性验证，确保增量开发的正确性
- 后端使用 Python FastAPI，前端使用 TypeScript React + Ant Design 6.3.0
