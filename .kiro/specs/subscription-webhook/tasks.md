# 实现计划：Subscription Webhook

## 概述

为现有订阅服务增加 Webhook 接收能力，包括：扩展 Application 模型（新增 webhook_secret）、新增 WebhookEventLog 数据模型、实现 HMAC-SHA256 签名验证、事件处理器、Webhook 端点、事件日志查询接口，以及管理后台的事件日志查看界面。所有实现集成到现有订阅服务（端口 8006）和管理服务（端口 8007）中。

## Tasks

- [x] 1. 数据模型与数据库迁移
  - [x] 1.1 创建 WebhookEventLog 模型并扩展 Application 模型
    - 在 `shared/models/webhook.py` 中创建 `WebhookEventLog` 模型，包含 event_id（唯一索引）、app_id、event_type、status、request_summary、response_summary、error_message、processed_at、created_at 字段
    - 在 `shared/models/application.py` 的 `Application` 模型中新增 `webhook_secret` 字段（String(255), nullable=True）
    - _Requirements: 5.1, 5.2, 1.1_

  - [x] 1.2 创建数据库迁移脚本
    - 在 `alembic/versions/007_add_webhook_tables.py` 中创建迁移：新增 `webhook_event_logs` 表，为 `applications` 表添加 `webhook_secret` 列
    - _Requirements: 5.1, 1.1_

  - [x] 1.3 创建 Webhook 事件 Pydantic 模型
    - 在 `services/subscription/webhook_schemas.py` 中定义 `WebhookEventPayload`、`EventData` 请求模型和响应模型
    - 包含 event_type 枚举校验（subscription.created/renewed/upgraded/downgraded/cancelled/expired）
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 2. Webhook 签名验证模块
  - [x] 2.1 实现 HMAC-SHA256 签名验证
    - 在 `services/subscription/webhook_auth.py` 中实现 `verify_webhook_signature(app_id, signature, body)` 函数
    - 通过 app_id 查找 Application，检查状态是否为 active
    - 使用 `webhook_secret` 计算 HMAC-SHA256，使用 `hmac.compare_digest` 恒定时间比较
    - 缺少头部返回 401，应用不存在/禁用返回 403，签名错误返回 401
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 2.2 编写签名验证属性测试
    - **Property 1: HMAC 签名验证往返一致性**
    - **Validates: Requirements 1.1**

  - [ ]* 2.3 编写认证头部缺失属性测试
    - **Property 2: 缺少认证头部返回 401**
    - **Validates: Requirements 1.2, 1.3**

  - [ ]* 2.4 编写无效/禁用应用属性测试
    - **Property 3: 无效或禁用应用返回 403**
    - **Validates: Requirements 1.4**

  - [ ]* 2.5 编写错误签名属性测试
    - **Property 4: 错误签名返回 401 并记录日志**
    - **Validates: Requirements 1.5**

- [x] 3. Webhook 事件处理器
  - [x] 3.1 实现事件处理器
    - 在 `services/subscription/webhook_handlers.py` 中实现六种事件类型的处理函数
    - `handle_subscription_created`：校验 AppUser 绑定和 plan_id 有效性，创建活跃订阅记录
    - `handle_subscription_renewed`：更新订阅到期日期
    - `handle_subscription_upgraded` / `handle_subscription_downgraded`：更新订阅计划
    - `handle_subscription_cancelled`：设置状态为 cancelled
    - `handle_subscription_expired`：设置状态为 expired
    - 每个处理函数校验 user_id 的 AppUser 绑定关系和 plan_id 有效性
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 3.2 编写创建订阅事件属性测试
    - **Property 6: 创建订阅事件生成活跃订阅**
    - **Validates: Requirements 3.1**

  - [ ]* 3.3 编写续费事件属性测试
    - **Property 7: 续费事件延长到期日期**
    - **Validates: Requirements 3.2**

  - [ ]* 3.4 编写升级/降级事件属性测试
    - **Property 8: 升级/降级事件更新订阅计划**
    - **Validates: Requirements 3.3**

  - [ ]* 3.5 编写取消/到期事件属性测试
    - **Property 9: 取消/到期事件设置终态状态**
    - **Validates: Requirements 3.4, 3.5**

  - [ ]* 3.6 编写无效用户/计划引用属性测试
    - **Property 10: 无效用户或计划引用返回 422**
    - **Validates: Requirements 3.6, 3.7**

- [x] 4. Checkpoint - 确保核心模块测试通过
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 5. Webhook 端点与幂等处理
  - [x] 5.1 实现 Webhook 接收端点
    - 在 `services/subscription/main.py` 中新增 `POST /api/v1/webhooks/subscription` 端点
    - 完整处理流程：读取原始请求体 → 签名验证 → Payload 校验 → 幂等检查（event_id）→ 分发到事件处理器 → 记录 Event Log → 返回响应
    - 成功返回 200 `{ event_id, status: "processed" }`，幂等命中返回 200 + 原始结果
    - 内部错误返回 500，Event Log 记录 failed 状态和完整错误信息
    - _Requirements: 4.1, 4.2, 6.1, 6.2, 6.3, 6.4, 5.1, 5.4_

  - [ ]* 5.2 编写 Payload 校验属性测试
    - **Property 5: 无效 Payload 返回 422**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

  - [ ]* 5.3 编写幂等性属性测试
    - **Property 11: 幂等性——重复事件不改变状态**
    - **Validates: Requirements 4.2**

  - [ ]* 5.4 编写事件日志完整性属性测试
    - **Property 12: 每个请求生成完整事件日志**
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 5.5 编写成功响应格式属性测试
    - **Property 14: 成功响应格式一致性**
    - **Validates: Requirements 6.2**

- [x] 6. 事件日志查询接口
  - [x] 6.1 实现事件日志分页查询端点
    - 在 `services/subscription/main.py` 中新增 `GET /api/v1/webhooks/events` 端点
    - 支持按 app_id、event_type、status、start_time、end_time 筛选，分页返回
    - _Requirements: 5.3_

  - [x] 6.2 在管理服务中新增事件日志代理接口
    - 在 `services/admin/main.py` 中新增管理端点，代理调用订阅服务的事件日志查询接口
    - _Requirements: 7.1_

  - [ ]* 6.3 编写事件日志筛选查询属性测试
    - **Property 13: 事件日志筛选查询正确性**
    - **Validates: Requirements 5.3**

- [x] 7. Checkpoint - 确保后端功能完整
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 8. 应用创建流程集成 webhook_secret
  - [x] 8.1 更新应用创建和重置密钥逻辑
    - 在 `services/admin/main.py` 的应用创建接口中，自动生成 32 字节随机 hex 的 `webhook_secret`
    - 新增 `POST /api/v1/admin/applications/{app_id}/reset-webhook-secret` 端点用于重置 webhook_secret
    - 应用详情接口返回 webhook_secret 字段
    - _Requirements: 1.1_

  - [x] 8.2 更新前端 API 服务
    - 在 `admin-ui/src/api/services.ts` 中为 applicationApi 新增 `resetWebhookSecret` 和 `getWebhookEvents` 方法
    - _Requirements: 7.1_

- [x] 9. 管理后台事件日志界面
  - [x] 9.1 创建 Webhook 事件日志面板组件
    - 在 `admin-ui/src/pages/panels/WebhookEventsPanel.tsx` 中创建事件日志列表组件
    - 展示事件ID、事件类型、处理状态、处理时间，支持按状态筛选
    - 点击事件展示完整详情（请求体摘要、错误信息）
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 9.2 在应用详情页集成事件日志 Tab
    - 在 `admin-ui/src/pages/panels/ApplicationDetail.tsx` 中新增 "Webhook 事件" Tab，嵌入 WebhookEventsPanel 组件
    - 展示 webhook_secret 字段和重置按钮
    - _Requirements: 7.1, 7.2_

- [x] 10. Final Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请向用户确认。

## Notes

- 标记 `*` 的子任务为可选，可跳过以加速 MVP 交付
- 每个任务引用了具体的需求编号，确保可追溯性
- 属性测试使用 `hypothesis` 库，测试文件统一放在 `tests/test_webhook_properties.py`
- 单元测试分布在 `tests/test_webhook_auth.py`、`tests/test_webhook_handlers.py`、`tests/test_webhook_endpoint.py`、`tests/test_webhook_events_query.py`
