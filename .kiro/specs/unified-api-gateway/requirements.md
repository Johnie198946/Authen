# 需求文档：统一 API 网关

## 简介

本功能旨在将现有微服务（认证、用户、权限、组织、订阅等）的能力整合为一套统一的对外 API 网关。管理员通过后台配置"应用"（即三方系统），每个应用获得独立的 `app_id` + `app_secret`，并可按需开启登录方式（邮箱、手机、微信、支付宝等）。三方系统只需对接统一 API，即可完成用户注册、登录、鉴权和权限管理，无需关心内部微服务拆分细节。

核心设计原则：
- 复用现有 Auth_Service、User_Service、Permission_Service 等微服务的全部能力
- 复用 shared/utils 中的 JWT、OAuth、加密、验证等工具模块
- 复用 shared/models 中的数据模型，新增 Application 相关模型
- 网关层仅负责凭证验证、请求路由、限流和审计，不重复实现业务逻辑

## 术语表

- **Gateway（网关）**: 统一 API 网关服务，作为三方系统对接的唯一入口，内部通过 HTTP 调用路由到各微服务
- **Application（应用）**: 管理员在后台注册的三方系统实体，包含 app_id、app_secret、启用的登录方式及权限范围配置
- **App_Credential（应用凭证）**: 由 app_id 和 app_secret 组成的密钥对，用于三方系统身份验证
- **Login_Method（登录方式）**: 应用可启用的用户认证方式，包括 email、phone、wechat、alipay、google、apple
- **Auth_Service（认证服务）**: 现有的认证微服务（端口 8001），处理注册、登录、OAuth、Token 管理
- **Permission_Service（权限服务）**: 现有的权限微服务（端口 8004），处理角色和权限管理
- **User_Service（用户服务）**: 现有的用户微服务（端口 8003），处理用户 CRUD
- **SSO_Service（单点登录服务）**: 现有的 SSO 微服务（端口 8002），处理会话管理
- **Admin_Panel（管理面板）**: 现有的 React + Ant Design 管理后台（端口 5173）
- **Rate_Limiter（限流器）**: 基于 Redis 的滑动窗口 API 请求频率限制组件
- **Scope（权限范围）**: 应用被授权可访问的 API 能力集合
- **App_User（应用用户）**: 通过某个 Application 注册的用户，与该 Application 存在绑定关系

## 需求

### 需求 1：应用注册与凭证管理

**用户故事：** 作为平台管理员，我希望在管理后台注册三方应用并生成凭证，以便三方系统能安全地对接统一 API。

#### 验收标准

1. WHEN 管理员提交应用注册请求（包含应用名称和描述），THE Admin_Panel SHALL 创建 Application 记录并生成唯一的 app_id（UUID 格式）和 app_secret（至少 32 字节的随机字符串）
2. THE Gateway SHALL 使用 shared/utils/crypto 模块以哈希形式存储 app_secret，原始 app_secret 仅在创建时返回一次
3. WHEN 管理员请求重置 app_secret，THE Gateway SHALL 生成新的 app_secret 并使旧凭证立即失效
4. WHEN 管理员禁用某个 Application，THE Gateway SHALL 拒绝该 Application 的所有 API 请求并返回 HTTP 403 状态码
5. THE Admin_Panel SHALL 提供应用列表页面，展示所有已注册应用的名称、app_id、状态和创建时间
6. WHEN 管理员删除某个 Application，THE Gateway SHALL 同时清除该应用在 Redis 中关联的所有缓存和会话数据

### 需求 2：应用登录方式配置

**用户故事：** 作为平台管理员，我希望为每个三方应用独立配置可用的登录方式，以便不同应用可以按需启用不同的认证渠道。

#### 验收标准

1. THE Admin_Panel SHALL 为每个 Application 提供登录方式配置界面，支持启用或禁用以下 Login_Method：email、phone、wechat、alipay、google、apple
2. WHEN 管理员启用 OAuth 类型的 Login_Method（wechat、alipay、google、apple），THE Admin_Panel SHALL 要求填写该提供商的 client_id 和 client_secret 配置
3. WHILE 某个 Login_Method 处于禁用状态，THE Gateway SHALL 拒绝通过该方式的注册和登录请求并返回 HTTP 400 状态码及明确的错误提示（包含该应用当前已启用的登录方式列表）
4. THE Gateway SHALL 将应用配置缓存到 Redis 中，并在应用配置变更后 5 秒内使配置缓存失效
5. WHEN 管理员保存 OAuth 配置，THE Admin_Panel SHALL 使用 shared/utils/crypto 模块以加密形式存储 client_secret，返回时仅展示末尾 4 位字符的脱敏信息

### 需求 3：统一认证 API

**用户故事：** 作为三方系统开发者，我希望通过统一的 API 完成用户注册和登录，无需了解平台内部的微服务架构。

#### 验收标准

1. WHEN 三方系统发送邮箱注册请求（包含 app_id、email、password、username），THE Gateway SHALL 验证 App_Credential 和 email Login_Method 启用状态后，调用 Auth_Service 的 /api/v1/auth/register/email 端点完成注册并返回用户 ID
2. WHEN 三方系统发送手机注册请求（包含 app_id、phone、password、username、verification_code），THE Gateway SHALL 验证 App_Credential 和 phone Login_Method 启用状态后，调用 Auth_Service 的 /api/v1/auth/register/phone 端点完成注册并返回用户 ID
3. WHEN 三方系统发送登录请求（包含 app_id、identifier、password），THE Gateway SHALL 验证 App_Credential 后调用 Auth_Service 的 /api/v1/auth/login 端点完成登录并返回 access_token、refresh_token 和用户信息
4. WHEN 三方系统发送 OAuth 登录请求（包含 app_id、provider、code、redirect_uri），THE Gateway SHALL 使用该 Application 配置的 OAuth 凭证（而非全局 OAuth 配置）调用 Auth_Service 的 /api/v1/auth/oauth/{provider} 端点完成认证并返回 Token
5. WHEN 三方系统发送 Token 刷新请求（包含 app_id、refresh_token），THE Gateway SHALL 验证 App_Credential 后调用 Auth_Service 的 /api/v1/auth/refresh 端点返回新的 access_token
6. IF App_Credential 验证失败，THEN THE Gateway SHALL 返回 HTTP 401 状态码和统一的错误描述"凭证无效"，不区分 app_id 不存在或 app_secret 错误
7. IF 请求的 Login_Method 未在该 Application 中启用，THEN THE Gateway SHALL 返回 HTTP 400 状态码并说明该登录方式未启用
8. WHEN 用户通过 Gateway 注册成功，THE Gateway SHALL 创建 App_User 绑定记录，将用户与注册时使用的 Application 关联

### 需求 4：API 请求鉴权

**用户故事：** 作为三方系统开发者，我希望通过统一的鉴权机制访问受保护的 API，以便安全地操作用户数据。

#### 验收标准

1. THE Gateway SHALL 支持两种鉴权方式：通过 HTTP Header（X-App-Id 和 X-App-Secret）传递应用凭证用于服务端调用，以及通过 Authorization: Bearer {access_token} 传递用户令牌用于用户级操作
2. WHEN 三方系统使用 app_id + app_secret 调用管理类 API，THE Gateway SHALL 验证凭证有效性并检查该应用的 Scope 权限
3. WHEN 三方系统使用 access_token 调用用户类 API，THE Gateway SHALL 使用 shared/utils/jwt 模块解析 Token 中的用户身份并验证 Token 有效性和签发应用归属
4. IF access_token 已过期，THEN THE Gateway SHALL 返回 HTTP 401 状态码和 error_code 为 token_expired 的 JSON 响应
5. IF access_token 格式无效或签名验证失败，THEN THE Gateway SHALL 返回 HTTP 401 状态码和 error_code 为 invalid_token 的 JSON 响应
6. THE Gateway SHALL 在签发的 Token payload 中包含 app_id 字段，确保用户 Token 与签发应用绑定，防止跨应用 Token 滥用

### 需求 5：应用权限范围管理

**用户故事：** 作为平台管理员，我希望为每个应用配置可访问的 API 范围，以便实现最小权限原则。

#### 验收标准

1. THE Admin_Panel SHALL 提供 Scope 配置界面，支持为每个 Application 分配以下权限范围：user:read、user:write、auth:login、auth:register、role:read、role:write、org:read、org:write
2. WHILE 某个 Application 未被授予特定 Scope，THE Gateway SHALL 拒绝该应用对应 API 的请求并返回 HTTP 403 状态码和 error_code 为 insufficient_scope 的 JSON 响应
3. WHEN 管理员修改 Application 的 Scope 配置，THE Gateway SHALL 在 5 秒内通过 Redis 缓存失效机制使新权限配置生效
4. THE Gateway SHALL 在每次 API 请求时从缓存或数据库中加载该 Application 的 Scope 列表，并验证请求的 API 是否在授权范围内

### 需求 6：API 限流与安全防护

**用户故事：** 作为平台运维人员，我希望对统一 API 实施限流和安全防护，以便保护平台免受滥用和攻击。

#### 验收标准

1. THE Rate_Limiter SHALL 使用 Redis 滑动窗口算法基于 app_id 维度实施请求频率限制，默认限制为每分钟 60 次请求
2. THE Admin_Panel SHALL 支持为每个 Application 单独配置限流阈值（每分钟请求次数）
3. WHEN 某个 Application 的请求频率超过限流阈值，THE Rate_Limiter SHALL 返回 HTTP 429 状态码并在响应头中包含 Retry-After 字段（值为距离限流窗口重置的秒数）
4. THE Gateway SHALL 在所有 API 响应中包含 X-RateLimit-Limit、X-RateLimit-Remaining 和 X-RateLimit-Reset 响应头
5. THE Gateway SHALL 复用 shared/utils/audit_log 模块记录所有 API 请求的审计日志，包含 app_id、请求路径、HTTP 方法、响应状态码和响应时间

### 需求 7：统一用户管理 API

**用户故事：** 作为三方系统开发者，我希望通过统一 API 管理用户信息和角色，以便在三方系统中实现用户管理功能。

#### 验收标准

1. WHEN 三方系统发送用户查询请求（包含 access_token 和 user_id），THE Gateway SHALL 调用 User_Service 的用户查询端点返回用户基本信息（id、username、email、phone、status）
2. WHEN 三方系统发送用户角色查询请求（包含 access_token 和 user_id），THE Gateway SHALL 调用 Permission_Service 的角色查询端点返回用户的角色列表
3. WHEN 三方系统发送权限检查请求（包含 access_token、user_id 和 permission_name），THE Gateway SHALL 调用 Permission_Service 的权限检查端点返回布尔类型的权限检查结果
4. WHEN 三方系统发送修改密码请求（包含 access_token、old_password 和 new_password），THE Gateway SHALL 调用 Auth_Service 的 /api/v1/auth/change-password 端点完成密码修改
5. IF 三方系统请求的用户不属于该 Application 的 App_User，THEN THE Gateway SHALL 返回 HTTP 403 状态码和 error_code 为 user_not_bound 的 JSON 响应

### 需求 8：网关服务部署与健康检查

**用户故事：** 作为平台运维人员，我希望网关服务具备完善的健康检查和监控能力，以便及时发现和处理服务异常。

#### 验收标准

1. THE Gateway SHALL 复用 shared/utils/health_check 模块提供 /health 端点，返回网关自身及所有下游微服务（Auth_Service、User_Service、Permission_Service、SSO_Service）的健康状态
2. WHEN 某个下游微服务不可用，THE Gateway SHALL 在健康检查响应中标记该服务为 unhealthy，并对该服务相关的 API 请求返回 HTTP 503 状态码和具体的服务不可用提示
3. THE Gateway SHALL 在启动时验证与所有下游微服务的连接，连接失败时记录错误日志但允许服务启动（降级模式）
4. THE Gateway SHALL 提供 /api/v1/gateway/info 端点，返回网关版本、支持的 API 版本列表和可用的 Login_Method 类型列表

### 需求 9：统一错误响应格式

**用户故事：** 作为三方系统开发者，我希望所有 API 错误响应遵循统一格式，以便简化错误处理逻辑。

#### 验收标准

1. THE Gateway SHALL 对所有错误响应使用统一的 JSON 格式，包含 error_code（机器可读的错误码）、message（人类可读的错误描述）和 request_id（请求追踪 ID）三个字段
2. WHEN 下游微服务返回错误，THE Gateway SHALL 将内部错误信息转换为统一格式，隐藏内部微服务的实现细节
3. THE Gateway SHALL 为每个 API 请求生成唯一的 request_id（UUID 格式），并在响应头 X-Request-Id 中返回
4. IF 下游微服务返回非预期的错误格式，THEN THE Gateway SHALL 返回 HTTP 502 状态码和 error_code 为 upstream_error 的统一错误响应
