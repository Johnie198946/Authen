# 实现计划：大模型配额管理（LLM Quota Management）

## 概述

为统一身份认证平台新增大模型配额管理能力，分三大模块实施：（1）配额核心引擎——扩展 SubscriptionPlan 模型、新增 AppQuotaOverride 和 QuotaUsage 数据模型、实现 Gateway quota_checker 中间件（Redis 原子计数器）、Admin 配额管理 API、配额重置调度、监控面板；（2）消息模板前端编辑器——基于已有后端 CRUD API 开发 Admin UI 模板管理面板；（3）配额查询 API + 前端对接指引——Gateway 新增 `/api/v1/quota/usage` 端点，扩展 IntegrationGuide 和 SecretDisplayModal。

## Tasks

- [x] 1. 数据模型扩展与数据库迁移
  - [x] 1.1 扩展 SubscriptionPlan 模型并新增 AppQuotaOverride、QuotaUsage 模型
    - 在 `shared/models/subscription.py` 的 `SubscriptionPlan` 模型上新增 `request_quota`（Integer, 默认 -1）、`token_quota`（BigInteger, 默认 -1）、`quota_period_days`（Integer, 默认 30）字段
    - 在 `shared/models/quota.py` 中创建 `AppQuotaOverride` 模型（application_id 唯一外键、request_quota、token_quota）
    - 在 `shared/models/quota.py` 中创建 `QuotaUsage` 模型（application_id 索引、billing_cycle_start/end、request/token quota limit/used、reset_type、created_at）
    - _Requirements: 1.1, 1.2, 1.3, 6.2, 10.1_

  - [x] 1.2 创建数据库迁移脚本
    - 在 `alembic/versions/` 中创建迁移：为 `subscription_plans` 表添加 request_quota、token_quota、quota_period_days 列；新增 `app_quota_overrides` 表和 `quota_usages` 表
    - _Requirements: 1.1, 1.2, 1.3, 6.2_

  - [ ]* 1.3 编写订阅计划配额字段往返属性测试
    - **Property 1: 订阅计划配额字段持久化往返**
    - **Validates: Requirements 1.1, 1.2, 1.3**

- [x] 2. Gateway 配额检查核心模块
  - [x] 2.1 实现 quota_checker 模块
    - 在 `services/gateway/quota_checker.py` 中实现 `QuotaCheckResult` 数据类（含 headers 属性生成 X-Quota-* 响应头）
    - 实现 `check_quota(app_id)` 函数：从 Redis 读取当前计数器，从 PostgreSQL（带缓存）读取配额配置，计算有效配额（AppQuotaOverride 优先于 SubscriptionPlan），判断是否放行
    - 实现 `deduct_request_quota(app_id)` 函数：使用 Redis INCRBY 原子递增请求计数器
    - 实现 `deduct_token_quota(app_id, token_usage)` 函数：使用 Redis INCRBYFLOAT 原子递增 Token 计数器，返回更新后的 QuotaCheckResult
    - 实现 `get_quota_usage(app_id)` 函数：从 Redis 读取实时数据供配额查询端点使用
    - 实现 Redis 降级策略：ConnectionError/TimeoutError 时返回 allowed=True 并记录 WARNING 日志
    - Redis Key 设计：`quota:{app_id}:requests`、`quota:{app_id}:tokens`、`quota:{app_id}:cycle_start`、`quota:{app_id}:config`，TTL = 剩余周期秒数 + 86400
    - 实现配额预警逻辑：使用率首次超过 80% 触发 `quota.warning` 事件，100% 触发 `quota.exhausted` 事件，通过 Redis 标记位 `quota:{app_id}:warning_sent:{level}` 防重复
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.5, 5.6, 9.1, 9.2, 9.3_

  - [ ]* 2.2 编写无限制配额放行属性测试
    - **Property 2: 无限制配额始终放行**
    - **Validates: Requirements 1.5**

  - [ ]* 2.3 编写未绑定计划拒绝属性测试
    - **Property 7: 未绑定计划的应用被拒绝**
    - **Validates: Requirements 2.4**

  - [ ]* 2.4 编写配额耗尽返回 429 属性测试
    - **Property 8: 配额耗尽返回 429**
    - **Validates: Requirements 3.2, 4.1, 4.2**

  - [ ]* 2.5 编写请求计数器精确递增属性测试
    - **Property 10: 请求计数器精确递增**
    - **Validates: Requirements 3.5**

  - [ ]* 2.6 编写 Token 计数器按实际消耗递增属性测试
    - **Property 11: Token 计数器按实际消耗递增**
    - **Validates: Requirements 3.6, 4.3, 4.4**

  - [ ]* 2.7 编写 Token 超额允许当次完成属性测试
    - **Property 12: Token 超额允许当次完成**
    - **Validates: Requirements 4.5**

  - [ ]* 2.8 编写 Redis 不可用优雅降级属性测试
    - **Property 15: Redis 不可用时优雅降级**
    - **Validates: Requirements 5.6**

  - [ ]* 2.9 编写手动覆盖优先级属性测试
    - **Property 21: 手动覆盖优先级**
    - **Validates: Requirements 10.1**

  - [ ]* 2.10 编写使用率状态分级属性测试
    - **Property 17: 使用率状态分级**
    - **Validates: Requirements 7.3, 7.4**

  - [ ]* 2.11 编写阈值事件单次触发属性测试
    - **Property 20: 阈值事件单次触发**
    - **Validates: Requirements 9.1, 9.2**

- [x] 3. Checkpoint - 确保配额核心模块测试通过
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 4. Gateway 端点集成
  - [x] 4.1 实现大模型 API 代理端点与配额查询端点
    - 在 `services/gateway/main.py` 中新增 `POST /api/v1/gateway/llm/{path:path}` 端点：复用现有认证链路（`_run_auth_pipeline`），在 rate_limit 之后调用 `check_quota` → `deduct_request_quota` → 转发下游 → 从响应提取 `token_usage` → `deduct_token_quota` → 注入 X-Quota-* 响应头
    - 在 `services/gateway/main.py` 中新增 `GET /api/v1/quota/usage` 端点：执行与其他 API 相同的认证流程（app_id + Bearer token），从 Redis 读取实时配额数据返回
    - 配额耗尽时返回 HTTP 429 + error_code + reset_at
    - 配额预警/耗尽时在响应头注入 `X-Quota-Warning: approaching_limit | exhausted`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 9.3, 12.1, 12.2, 12.6_

  - [ ]* 4.2 编写配额响应头完整性属性测试
    - **Property 9: 配额响应头完整性**
    - **Validates: Requirements 3.3, 3.4, 9.3**

  - [ ]* 4.3 编写配额查询端点数据一致性属性测试
    - **Property 24: 配额查询端点数据一致性**
    - **Validates: Requirements 12.1, 12.6**

- [x] 5. Admin Service 配额管理 API
  - [x] 5.1 实现配额管理后端 API
    - 在 `services/admin/main.py` 中新增以下端点：
      - `GET /api/v1/admin/quota/overview`：所有应用配额使用概览（从 Redis 读取实时数据，支持按使用率排序）
      - `GET /api/v1/admin/quota/{app_id}`：单个应用配额详情
      - `PUT /api/v1/admin/quota/{app_id}/override`：手动调整应用配额上限（写入 AppQuotaOverride，立即更新 Redis 缓存配置，记录审计日志）
      - `POST /api/v1/admin/quota/{app_id}/reset`：手动重置应用配额（Redis 计数器归零，持久化当前使用数据到 QuotaUsage，记录审计日志）
      - `GET /api/v1/admin/quota/{app_id}/history`：应用配额使用历史（支持按时间范围筛选，分页返回）
    - 扩展现有订阅计划 CRUD 端点，支持 request_quota、token_quota、quota_period_days 字段的创建和更新，验证值 >= -1
    - _Requirements: 1.4, 1.6, 6.3, 7.1, 7.5, 8.3, 8.4, 10.1, 10.2, 10.3, 10.4_

  - [ ]* 5.2 编写非法配额值拒绝属性测试
    - **Property 3: 非法配额值被拒绝**
    - **Validates: Requirements 1.6**

  - [ ]* 5.3 编写计划绑定初始化配额属性测试
    - **Property 4: 计划绑定初始化配额**
    - **Validates: Requirements 2.1**

  - [ ]* 5.4 编写计划升级立即生效属性测试
    - **Property 5: 计划升级立即生效且保留已用量**
    - **Validates: Requirements 2.2**

  - [ ]* 5.5 编写计划降级延迟生效属性测试
    - **Property 6: 计划降级延迟生效**
    - **Validates: Requirements 2.3**

  - [ ]* 5.6 编写历史记录查询过滤属性测试
    - **Property 16: 历史记录查询过滤正确性**
    - **Validates: Requirements 6.3**

  - [ ]* 5.7 编写使用率排序正确性属性测试
    - **Property 18: 使用率排序正确性**
    - **Validates: Requirements 7.5**

  - [ ]* 5.8 编写配额变更审计日志完整性属性测试
    - **Property 19: 配额变更审计日志完整性**
    - **Validates: Requirements 8.4, 10.4**

- [x] 6. 配额重置调度与 Webhook 通知
  - [x] 6.1 实现配额重置定时任务
    - 在 `services/subscription/main.py` 中新增 `process_quota_resets(db)` 函数，复用现有 `process_expired_subscriptions` 的调度模式
    - 查询所有活跃应用的配额配置，检查当前周期是否已结束
    - 持久化当前周期使用数据到 QuotaUsage 表，重置 Redis 计数器，更新周期开始时间
    - 记录审计日志（reset_type=auto）
    - _Requirements: 8.1, 8.2, 8.4, 6.1_

  - [x] 6.2 实现配额超限 Webhook 通知
    - 复用现有 `services/subscription/webhook_handlers.py` 的 Webhook 推送机制
    - 新增事件类型 `quota.warning`（80% 预警）和 `quota.exhausted`（100% 耗尽）
    - 在 quota_checker 中检测阈值并触发 Webhook 推送（如应用配置了回调地址）
    - _Requirements: 9.1, 9.2, 9.4_

  - [ ]* 6.3 编写配额重置归零并持久化属性测试
    - **Property 13: 配额重置归零并持久化**
    - **Validates: Requirements 5.4, 6.1, 6.2, 8.1, 8.2, 8.3, 10.2**

  - [ ]* 6.4 编写 Redis Key TTL 正确性属性测试
    - **Property 14: Redis Key TTL 正确性**
    - **Validates: Requirements 5.5**

- [x] 7. Checkpoint - 确保后端功能完整
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 8. Admin UI 配额监控面板
  - [x] 8.1 创建配额监控面板组件
    - 在 `admin-ui/src/pages/panels/QuotaMonitorPanel.tsx` 中创建配额监控面板
    - 表格展示所有应用的当前计费周期配额使用概览（应用名称、请求次数使用率、Token 使用率、计费周期、重置时间）
    - 使用 Ant Design Progress 组件展示请求次数和 Token 使用率进度条
    - 使用率 > 80% 黄色警告样式（status="warning"），= 100% 红色告警样式（status="exception"）
    - 支持按请求次数使用率或 Token 使用率降序排列
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 8.2 创建配额使用历史面板
    - 在 `admin-ui/src/pages/panels/QuotaHistoryPanel.tsx` 中创建历史面板
    - 支持按时间范围和应用 ID 筛选
    - 以表格和折线图（Ant Design Charts 或 recharts）两种形式展示配额使用趋势
    - _Requirements: 6.3, 6.4_

  - [x] 8.3 扩展订阅计划表单
    - 在现有 `SubscriptionsPanel.tsx` 的创建/编辑表单中新增 request_quota、token_quota、quota_period_days 输入字段
    - 验证 request_quota 和 token_quota >= -1，quota_period_days > 0
    - 值为 -1 时显示"无限制"提示
    - _Requirements: 1.4, 1.6_

  - [x] 8.4 创建配额手动调整对话框
    - 在配额监控面板中为每个应用提供"调整配额"和"重置配额"操作按钮
    - 调整配额：弹出确认对话框，展示调整前后的配额对比信息，提交后调用 `PUT /api/v1/admin/quota/{app_id}/override`
    - 重置配额：弹出确认对话框，提交后调用 `POST /api/v1/admin/quota/{app_id}/reset`
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 8.5 在 Dashboard 和路由中集成配额面板
    - 在 `admin-ui/src/api/services.ts` 中新增 quotaApi（overview、detail、override、reset、history 方法）
    - 在 Dashboard 中添加配额监控面板入口
    - _Requirements: 7.1_

- [x] 9. Admin UI 消息模板编辑面板
  - [x] 9.1 创建消息模板管理面板
    - 在 `admin-ui/src/pages/panels/MessageTemplatePanel.tsx` 中创建模板管理面板
    - 按类型（email/sms）分 Tab 展示所有模板列表
    - 模板编辑器：支持编辑模板名称、主题（仅邮件）、内容和变量说明
    - Jinja2 变量插入辅助：展示该模板可用的变量列表，点击变量名自动插入 `{{ variable_name }}` 到光标位置
    - 实时预览功能：提供示例变量值输入区域，使用简单的字符串替换在前端渲染预览效果
    - 支持创建新模板和删除自定义模板
    - 系统内置模板（email_verification、password_reset、subscription_reminder、email_verification_code）不可删除，隐藏删除按钮
    - 编辑短信模板时显示云厂商模板审核提示信息
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [x] 9.2 在 Dashboard 和路由中集成模板面板
    - 在 `admin-ui/src/api/services.ts` 中新增 templateApi（list、get、create、update、delete 方法），对接已有 `/api/v1/admin/templates` 端点
    - 在 Dashboard 中添加模板管理面板入口
    - _Requirements: 11.1_

  - [ ]* 9.3 编写模板预览渲染正确性属性测试
    - **Property 22: 模板预览渲染正确性**
    - **Validates: Requirements 11.4**

  - [ ]* 9.4 编写系统内置模板不可删除属性测试
    - **Property 23: 系统内置模板不可删除**
    - **Validates: Requirements 11.6**

- [x] 10. Checkpoint - 确保前端面板功能完整
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 11. 前端对接指引扩展
  - [x] 11.1 扩展 IntegrationGuide 组件
    - 在 `admin-ui/src/pages/panels/IntegrationGuide.tsx` 中新增"配额管理 API"章节
    - 包含 `GET /api/v1/quota/usage` 端点的请求示例（含 Authorization header）和完整响应示例
    - 说明配额相关响应头（X-Quota-Request-Limit、X-Quota-Request-Remaining、X-Quota-Request-Reset、X-Quota-Token-Limit、X-Quota-Token-Remaining、X-Quota-Token-Reset、X-Quota-Warning）的含义和使用方式
    - _Requirements: 12.3, 12.4_

  - [x] 11.2 扩展 SecretDisplayModal 组件
    - 在 `admin-ui/src/pages/panels/wizard/SecretDisplayModal.tsx` 中新增配额 API 快速对接代码示例
    - 包含使用 Bearer token 调用 `/api/v1/quota/usage` 的 Python/curl 代码片段
    - _Requirements: 12.5_

- [x] 12. Final Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请向用户确认。

## Notes

- 标记 `*` 的子任务为可选属性测试，可跳过以加速 MVP 交付
- 每个任务引用了具体的需求编号，确保可追溯性
- 属性测试使用 Hypothesis 库，测试文件按设计文档规划分布在 `tests/test_quota_checker_properties.py`、`tests/test_quota_reset_properties.py`、`tests/test_quota_admin_properties.py`、`tests/test_quota_gateway_properties.py`、`tests/test_template_properties.py`、`tests/test_subscription_quota_properties.py`
- 单元测试分布在 `tests/test_quota_checker.py`、`tests/test_quota_reset.py`、`tests/test_quota_admin_api.py`、`tests/test_quota_gateway.py`、`tests/test_template_panel.py`
- 后端使用 Python/FastAPI，前端使用 React + Ant Design + TypeScript
- 所有 Python 命令使用 `python3`
