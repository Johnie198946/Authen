# 需求文档：大模型流量管理（LLM Quota Management）

## 简介

本功能为统一身份认证和权限管理平台新增大模型配额管理能力。与现有的 rate_limit（每分钟请求频率限制，防止瞬时过载）不同，本功能面向商业化计费场景，管理三方应用对大模型 API 的长期配额——包括请求次数（request）和 Token 消耗量（token）。配额与订阅计划绑定，不同订阅等级对应不同额度。Gateway 层负责实时配额检查与扣减，管理后台提供配额的配置与监控界面。

## 术语表

- **Gateway**: 统一 API 网关服务（端口 8008），所有三方应用请求的唯一入口
- **Quota_Manager**: 配额管理模块，负责配额的检查、扣减和重置逻辑
- **Subscription_Plan**: 订阅计划，定义订阅等级及其包含的功能特性和配额
- **Application**: 三方应用，通过 app_id 和 app_secret 接入平台
- **Request_Quota**: 请求次数配额，限制应用在一个计费周期内可发起的大模型 API 请求总次数
- **Token_Quota**: Token 消耗配额，限制应用在一个计费周期内可消耗的大模型 Token 总量
- **Billing_Cycle**: 计费周期，配额的重置周期（月度或自定义天数）
- **Quota_Usage**: 配额使用记录，记录应用在当前计费周期内已消耗的请求次数和 Token 量
- **Admin_UI**: 管理后台前端界面（React + Ant Design）
- **Redis_Cache**: Redis 缓存层，用于存储实时配额计数器以实现高性能扣减

## 需求

### 需求 1：订阅计划配额配置

**用户故事：** 作为平台管理员，我想在订阅计划中配置大模型的请求次数和 Token 配额，以便不同订阅等级的应用获得不同的大模型使用额度。

#### 验收标准

1. THE Subscription_Plan SHALL 包含 request_quota 字段，定义每个计费周期内允许的最大请求次数
2. THE Subscription_Plan SHALL 包含 token_quota 字段，定义每个计费周期内允许的最大 Token 消耗量
3. THE Subscription_Plan SHALL 包含 quota_period_days 字段，定义配额重置的计费周期天数，默认值为 30
4. WHEN 管理员创建或更新 Subscription_Plan 时，THE Admin_UI SHALL 提供 request_quota、token_quota 和 quota_period_days 的输入表单
5. WHEN request_quota 或 token_quota 的值为 -1 时，THE Quota_Manager SHALL 将该配额视为无限制
6. WHEN 管理员提交的 request_quota 或 token_quota 值小于 -1 时，THE Admin_UI SHALL 拒绝提交并显示验证错误信息

### 需求 2：应用配额初始化与绑定

**用户故事：** 作为平台管理员，我想让应用的大模型配额自动继承其订阅计划的配置，以便配额管理与订阅体系保持一致。

#### 验收标准

1. WHEN 应用绑定或变更 Subscription_Plan 时，THE Quota_Manager SHALL 根据新计划的 request_quota 和 token_quota 初始化或更新应用的配额上限
2. WHEN 应用的 Subscription_Plan 升级时，THE Quota_Manager SHALL 立即生效新的配额上限，并保留当前已使用量
3. WHEN 应用的 Subscription_Plan 降级时，THE Quota_Manager SHALL 在当前计费周期结束后生效新的配额上限
4. IF 应用未绑定任何 Subscription_Plan，THEN THE Quota_Manager SHALL 拒绝该应用的大模型 API 请求并返回错误码 quota_not_configured

### 需求 3：Gateway 配额实时检查

**用户故事：** 作为平台运维人员，我想在 Gateway 层对每个大模型 API 请求进行实时配额检查，以便在配额耗尽时及时拦截请求。

#### 验收标准

1. WHEN Gateway 收到大模型 API 请求时，THE Quota_Manager SHALL 在路由到下游服务之前检查该应用的 Request_Quota 剩余量
2. IF 应用的 Request_Quota 剩余量为 0，THEN THE Gateway SHALL 返回 HTTP 429 状态码，错误码为 request_quota_exceeded，并在响应体中包含配额重置时间
3. THE Gateway SHALL 在每个大模型 API 响应中包含以下配额相关响应头：X-Quota-Request-Limit、X-Quota-Request-Remaining、X-Quota-Request-Reset
4. THE Gateway SHALL 在每个大模型 API 响应中包含以下 Token 配额响应头：X-Quota-Token-Limit、X-Quota-Token-Remaining、X-Quota-Token-Reset
5. WHEN 大模型 API 请求成功处理后，THE Quota_Manager SHALL 将该应用的 Request_Quota 已使用量加 1
6. WHEN 大模型 API 请求成功处理后，THE Quota_Manager SHALL 根据下游服务返回的实际 Token 消耗量更新该应用的 Token_Quota 已使用量

### 需求 4：Token 配额实时检查与扣减

**用户故事：** 作为平台运维人员，我想在 Gateway 层对大模型 API 请求进行 Token 配额检查，以便在 Token 配额耗尽时拦截请求。

#### 验收标准

1. WHEN Gateway 收到大模型 API 请求时，THE Quota_Manager SHALL 检查该应用的 Token_Quota 剩余量是否大于 0
2. IF 应用的 Token_Quota 剩余量为 0，THEN THE Gateway SHALL 返回 HTTP 429 状态码，错误码为 token_quota_exceeded，并在响应体中包含配额重置时间
3. WHEN 下游服务返回的响应中包含 token_usage 字段时，THE Quota_Manager SHALL 使用该值作为本次请求的 Token 消耗量
4. IF 下游服务返回的响应中不包含 token_usage 字段，THEN THE Quota_Manager SHALL 使用默认估算值 0 作为本次请求的 Token 消耗量
5. WHEN 单次请求的 Token 消耗量导致累计使用量超过 Token_Quota 上限时，THE Quota_Manager SHALL 允许本次请求完成但标记该应用的 Token_Quota 为已耗尽状态

### 需求 5：配额计数器的高性能存储

**用户故事：** 作为平台架构师，我想使用 Redis 作为配额计数器的实时存储，以便在高并发场景下保证配额检查和扣减的性能。

#### 验收标准

1. THE Quota_Manager SHALL 使用 Redis_Cache 存储每个应用的当前计费周期内的请求次数计数器和 Token 消耗量计数器
2. THE Quota_Manager SHALL 使用 Redis INCRBY 命令实现请求次数的原子递增
3. THE Quota_Manager SHALL 使用 Redis INCRBYFLOAT 命令实现 Token 消耗量的原子递增
4. WHEN 新的计费周期开始时，THE Quota_Manager SHALL 重置 Redis 中对应应用的配额计数器，并将上一周期的使用数据持久化到 PostgreSQL
5. THE Quota_Manager SHALL 为 Redis 中的配额计数器 key 设置过期时间，过期时间等于当前计费周期的剩余秒数加 86400 秒的安全余量
6. IF Redis 不可用，THEN THE Quota_Manager SHALL 降级为允许请求通过，并记录告警日志

### 需求 6：配额使用记录持久化

**用户故事：** 作为平台管理员，我想查看每个应用的历史配额使用情况，以便进行用量分析和计费审计。

#### 验收标准

1. THE Quota_Manager SHALL 在每个计费周期结束时将该周期的配额使用汇总数据写入 PostgreSQL 的 Quota_Usage 表
2. THE Quota_Usage 表 SHALL 包含以下字段：应用 ID、计费周期开始时间、计费周期结束时间、请求次数上限、已使用请求次数、Token 上限、已使用 Token 量
3. WHEN 管理员查询应用的配额使用历史时，THE Admin_UI SHALL 支持按时间范围和应用 ID 进行筛选
4. THE Admin_UI SHALL 以表格和折线图两种形式展示应用的配额使用趋势

### 需求 7：管理后台配额监控面板

**用户故事：** 作为平台管理员，我想在管理后台实时查看各应用的配额使用情况，以便及时发现配额即将耗尽的应用。

#### 验收标准

1. THE Admin_UI SHALL 提供配额监控面板，展示所有应用的当前计费周期配额使用概览
2. THE Admin_UI SHALL 在配额监控面板中以进度条形式展示每个应用的请求次数使用率和 Token 使用率
3. WHEN 应用的请求次数或 Token 使用率超过 80% 时，THE Admin_UI SHALL 以黄色警告样式高亮显示该应用
4. WHEN 应用的请求次数或 Token 使用率达到 100% 时，THE Admin_UI SHALL 以红色告警样式高亮显示该应用
5. THE Admin_UI SHALL 提供配额使用率排序功能，支持按请求次数使用率或 Token 使用率降序排列

### 需求 8：配额重置机制

**用户故事：** 作为平台运维人员，我想让配额在每个计费周期自动重置，以便应用在新周期获得完整配额。

#### 验收标准

1. WHEN 应用的当前计费周期结束时，THE Quota_Manager SHALL 自动重置该应用的请求次数计数器和 Token 消耗量计数器
2. WHEN 配额重置发生时，THE Quota_Manager SHALL 将重置前的使用数据持久化到 Quota_Usage 表
3. WHEN 管理员手动触发配额重置时，THE Quota_Manager SHALL 立即重置指定应用的配额计数器，并将当前使用数据持久化
4. THE Quota_Manager SHALL 在配额重置完成后记录审计日志，包含应用 ID、重置类型（自动/手动）和重置前的使用量

### 需求 9：配额超限通知

**用户故事：** 作为三方应用开发者，我想在配额即将耗尽或已耗尽时收到通知，以便及时采取措施（升级订阅或优化用量）。

#### 验收标准

1. WHEN 应用的请求次数或 Token 使用率首次超过 80% 时，THE Quota_Manager SHALL 触发一次配额预警事件
2. WHEN 应用的请求次数或 Token 配额耗尽时，THE Quota_Manager SHALL 触发一次配额耗尽事件
3. THE Gateway SHALL 在配额预警和耗尽事件触发时，在响应头中包含 X-Quota-Warning 字段，值为 approaching_limit 或 exhausted
4. IF 应用配置了 Webhook 回调地址，THEN THE Quota_Manager SHALL 通过 Webhook 将配额预警和耗尽事件推送给应用

### 需求 10：管理员手动调整配额

**用户故事：** 作为平台管理员，我想手动调整特定应用的配额上限或已使用量，以便处理特殊业务场景（如临时增加额度、修正计量错误）。

#### 验收标准

1. WHEN 管理员在 Admin_UI 中调整应用的配额上限时，THE Quota_Manager SHALL 立即更新该应用的配额上限，覆盖订阅计划的默认值
2. WHEN 管理员在 Admin_UI 中重置应用的已使用量时，THE Quota_Manager SHALL 将 Redis 中的对应计数器归零
3. THE Admin_UI SHALL 在配额调整操作前显示确认对话框，包含调整前后的配额对比信息
4. THE Quota_Manager SHALL 在每次手动配额调整后记录审计日志，包含操作人、调整类型、调整前后的值

### 需求 11：邮件/短信推送模板前端编辑

**用户故事：** 作为平台管理员，我想在管理后台直接编辑邮件和短信推送模板，保存后系统自动使用新模板发送消息，以便无需修改代码即可调整通知内容。

**可行性评估：**
- 后端已完全支持：`MessageTemplate` 模型（`shared/models/system.py`）存储模板，Admin 服务已有完整 CRUD API（`/api/v1/admin/templates`）
- 模板使用 Jinja2 语法，支持变量替换（如 `{{ verification_code }}`、`{{ plan_name }}`）
- `EmailService` 和 `SMSService` 已从数据库读取模板并渲染，保存即生效
- 不需要对接阿里云来管理模板。阿里云邮件推送走 SMTP 协议，模板完全由平台自己管理；阿里云短信有自己的模板审核机制（`template_code`），但平台内部模板编辑器与之独立——平台模板用于组织内容和变量，阿里云模板用于合规审核
- 唯一需要开发的是前端模板编辑面板

#### 验收标准

1. THE Admin_UI SHALL 提供消息模板管理面板，支持按类型（email/sms）分 Tab 展示所有模板
2. THE Admin_UI SHALL 提供模板编辑器，支持编辑模板名称、主题（邮件）、内容和变量说明
3. THE Admin_UI SHALL 在模板编辑器中提供 Jinja2 变量插入辅助功能，展示该模板可用的变量列表（如 `{{ verification_code }}`、`{{ email }}`）
4. THE Admin_UI SHALL 提供模板实时预览功能，管理员可输入示例变量值查看渲染效果
5. WHEN 管理员保存模板后，THE EmailService 和 SMSService SHALL 在下次发送时自动使用更新后的模板内容，无需重启服务
6. THE Admin_UI SHALL 支持创建新模板和删除自定义模板，但系统内置模板（email_verification、password_reset、subscription_reminder、email_verification_code）不可删除
7. WHEN 管理员编辑短信模板时，THE Admin_UI SHALL 显示提示信息，说明如果使用阿里云/腾讯云短信服务，还需在对应云厂商控制台申请并审核短信模板（template_code/template_id）

### 需求 12：配额查询 API 通过统一 Gateway 对外提供 + 前端对接指引

**用户故事：** 作为三方应用开发者，我想通过统一的 Gateway API 查询我的应用的配额使用情况，并在应用管理页面看到完整的对接文档，以便快速集成配额管理功能。

**可行性评估：**
- Gateway（端口 8008）已有完整的认证链路（app_id + app_secret → JWT token → scope 检查 → rate_limit），新增配额查询端点只需在 Gateway 中添加一个路由
- 现有的 `IntegrationGuide.tsx` 和 `SecretDisplayModal.tsx` 已提供 API 对接指引框架，可直接扩展
- 后端架构完全支持，无需额外改造

#### 验收标准

1. THE Gateway SHALL 提供 `GET /api/v1/quota/usage` 端点，返回当前应用的配额使用情况，包含 request_quota_limit、request_quota_used、request_quota_remaining、token_quota_limit、token_quota_used、token_quota_remaining、billing_cycle_start、billing_cycle_end、billing_cycle_reset
2. THE Gateway SHALL 对 `/api/v1/quota/usage` 端点执行与其他 API 相同的认证流程（app_id + Bearer token）
3. THE Admin_UI SHALL 在应用详情页的 API 集成指南中增加"配额管理 API"章节，包含配额查询端点的请求示例和响应示例
4. THE Admin_UI SHALL 在 API 集成指南中说明配额相关响应头（X-Quota-Request-Limit、X-Quota-Request-Remaining、X-Quota-Token-Limit、X-Quota-Token-Remaining 等）的含义和使用方式
5. THE Admin_UI SHALL 在应用创建成功后的密钥展示弹窗（SecretDisplayModal）中包含配额 API 的快速对接代码示例
6. WHEN 三方应用调用 `/api/v1/quota/usage` 时，THE Gateway SHALL 返回实时数据（从 Redis 读取当前计数器值）
