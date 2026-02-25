# 需求文档

## 简介

本功能为统一API平台的订阅服务增加标准化的 Webhook 接收能力。第三方系统在完成应用配置后已获得 app_id 和 app_secret 凭证，Webhook 推送复用这套已有的应用认证体系。当用户在第三方平台完成订阅操作后，第三方系统使用已有的应用凭证，按照平台提供的标准化规范推送订阅事件，平台接收并自动完成对应用户的订阅管理变更（创建、续费、升级、降级、取消等）。

## 术语表

- **Webhook_Receiver**：订阅服务中负责接收和处理第三方推送事件的端点模块
- **Webhook_Event**：第三方系统按照标准化规范推送到平台的订阅事件消息
- **Event_Payload**：Webhook 事件中携带的标准化数据结构，包含事件类型、用户标识、订阅计划等信息
- **Application**：平台已有的应用实体，包含 app_id 和 app_secret，第三方系统通过应用配置向导获得这些凭证
- **Event_Log**：记录所有接收到的 Webhook 事件及其处理结果的持久化日志
- **Idempotency_Key**：Webhook 事件中的唯一标识符，用于防止重复处理同一事件
- **Subscription_Service**：现有的订阅管理服务，负责订阅计划和用户订阅的 CRUD 操作
- **AppUser**：平台已有的应用-用户绑定关系，记录哪些用户属于哪个应用

## 约束

- Webhook 认证必须复用现有的 Application 凭证体系（app_id + app_secret），不引入独立的 Webhook Source 注册机制
- 第三方系统已通过应用配置向导获得 app_id 和 app_secret，并已完成对接
- 用户标识映射通过已有的 AppUser 绑定关系实现，不引入额外的外部用户映射表

## 需求

### 需求 1：基于应用凭证的 Webhook 认证

**用户故事：** 作为已对接的第三方系统，我希望使用已有的 app_id 和 app_secret 凭证来推送 Webhook 事件，无需额外注册或获取新的密钥。

#### 验收标准

1. THE Webhook_Receiver SHALL 使用 HMAC-SHA256 算法验证请求签名，签名密钥为 Application 对应的 app_secret
2. THE Webhook_Receiver SHALL 要求每个 Webhook 请求携带 X-App-Id 头部（标识应用）和 X-Webhook-Signature 头部（请求签名）
3. WHEN 请求中缺少 X-App-Id 或 X-Webhook-Signature 头部时，THE Webhook_Receiver SHALL 返回 HTTP 401 状态码
4. WHEN X-App-Id 对应的 Application 不存在或状态为 disabled 时，THE Webhook_Receiver SHALL 返回 HTTP 403 状态码
5. WHEN 签名验证失败时，THE Webhook_Receiver SHALL 返回 HTTP 401 状态码并记录验证失败事件到 Event_Log
6. THE Webhook_Receiver SHALL 使用恒定时间比较算法验证签名，防止时序攻击

### 需求 2：标准化事件模型

**用户故事：** 作为第三方系统集成开发者，我希望平台提供清晰的标准化事件数据格式规范，以便我能按照规范推送订阅事件。

#### 验收标准

1. THE Webhook_Receiver SHALL 定义标准化的 Event_Payload 结构，包含以下必填字段：event_id（唯一事件标识）、event_type（事件类型）、timestamp（事件发生时间 ISO 8601 格式）、data（事件数据）
2. THE Webhook_Receiver SHALL 支持以下 event_type 值：subscription.created（新建订阅）、subscription.renewed（续费）、subscription.upgraded（升级）、subscription.downgraded（降级）、subscription.cancelled（取消）、subscription.expired（到期）
3. THE Webhook_Receiver SHALL 要求 data 字段包含以下信息：user_id（平台用户ID，通过 AppUser 绑定关系已知）、plan_id（平台订阅计划ID）、effective_date（生效日期）、expiry_date（到期日期，取消和到期事件可选）
4. WHEN 接收到不符合标准化格式的 Event_Payload 时，THE Webhook_Receiver SHALL 返回 HTTP 422 状态码和具体的字段校验错误信息

### 需求 3：Webhook 事件接收与处理

**用户故事：** 作为平台系统，我希望在接收到合法的 Webhook 事件后自动完成用户订阅状态变更，以实现第三方订阅与平台订阅的自动同步。

#### 验收标准

1. WHEN 接收到 event_type 为 subscription.created 的合法事件时，THE Subscription_Service SHALL 为对应用户创建新的活跃订阅记录
2. WHEN 接收到 event_type 为 subscription.renewed 的合法事件时，THE Subscription_Service SHALL 延长对应用户的订阅到期日期
3. WHEN 接收到 event_type 为 subscription.upgraded 或 subscription.downgraded 的合法事件时，THE Subscription_Service SHALL 更新对应用户的订阅计划为目标计划
4. WHEN 接收到 event_type 为 subscription.cancelled 的合法事件时，THE Subscription_Service SHALL 将对应用户的订阅状态设置为 cancelled
5. WHEN 接收到 event_type 为 subscription.expired 的合法事件时，THE Subscription_Service SHALL 将对应用户的订阅状态设置为 expired
6. IF Event_Payload 中的 user_id 不属于该 Application 的 AppUser 绑定关系时，THEN THE Webhook_Receiver SHALL 返回 HTTP 422 状态码并在 Event_Log 中记录用户不属于该应用的错误
7. IF Event_Payload 中的 plan_id 对应的订阅计划不存在或已停用时，THEN THE Webhook_Receiver SHALL 返回 HTTP 422 状态码并在 Event_Log 中记录计划无效的错误

### 需求 4：幂等处理

**用户故事：** 作为平台系统，我希望能正确处理第三方系统的重复推送，避免同一事件被多次处理导致数据异常。

#### 验收标准

1. THE Webhook_Receiver SHALL 使用 Event_Payload 中的 event_id 作为 Idempotency_Key
2. WHEN 接收到已处理过的 event_id 时，THE Webhook_Receiver SHALL 返回 HTTP 200 状态码和原始处理结果，不再重复执行订阅变更操作
3. THE Webhook_Receiver SHALL 保留已处理事件的 Idempotency_Key 至少 72 小时

### 需求 5：事件日志

**用户故事：** 作为平台管理员，我希望能查看所有 Webhook 事件的接收和处理记录，以便排查问题和审计。

#### 验收标准

1. THE Webhook_Receiver SHALL 为每个接收到的 Webhook 请求创建一条 Event_Log 记录
2. THE Event_Log SHALL 包含以下信息：事件ID、应用ID（app_id）、事件类型、处理状态（pending、success、failed、duplicate）、请求体摘要、错误信息（如有）、处理时间戳
3. THE Webhook_Receiver SHALL 提供 Event_Log 的分页查询接口，支持按应用、事件类型、处理状态和时间范围筛选
4. IF 事件处理过程中发生异常，THEN THE Webhook_Receiver SHALL 将 Event_Log 状态设置为 failed 并记录完整的错误信息

### 需求 6：Webhook 端点与响应规范

**用户故事：** 作为第三方系统集成开发者，我希望平台提供明确的 Webhook 端点和响应规范，以便我能正确集成。

#### 验收标准

1. THE Webhook_Receiver SHALL 在路径 /api/v1/webhooks/subscription 提供 POST 端点接收订阅事件
2. WHEN 事件处理成功时，THE Webhook_Receiver SHALL 返回 HTTP 200 状态码和包含 event_id、status 为 processed 的 JSON 响应
3. THE Webhook_Receiver SHALL 在 5 秒内完成事件接收确认并返回响应
4. IF 事件处理过程中发生内部错误，THEN THE Webhook_Receiver SHALL 返回 HTTP 500 状态码，第三方系统可据此进行重试

### 需求 7：管理后台事件日志查看

**用户故事：** 作为平台管理员，我希望在管理后台能查看应用的 Webhook 事件日志，以便监控第三方订阅推送的状态。

#### 验收标准

1. THE 管理后台 SHALL 在应用详情页中展示该应用的 Webhook 事件日志列表
2. THE 事件日志列表 SHALL 展示事件ID、事件类型、处理状态、处理时间，并支持按状态筛选
3. WHEN 管理员点击某条事件日志时，THE 管理后台 SHALL 展示该事件的完整详情，包括请求体摘要和错误信息
