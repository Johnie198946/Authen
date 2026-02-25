# 第三方应用对接指南

## 概述

统一身份认证平台通过 API 网关（端口 8008）为第三方应用提供用户认证、权限管理等能力。所有 API 请求必须经过网关，不允许直接访问内部微服务。

**网关地址**: `http://<host>:8008`  
**API 版本**: v1  
**基础路径**: `/api/v1/gateway`

---

## 对接前准备

### 1. 获取应用凭证

在管理后台创建应用后，会获得以下凭证：

| 字段 | 说明 |
|------|------|
| `app_id` | 应用唯一标识 |
| `app_secret` | 应用密钥（仅创建时显示一次，请妥善保管） |

### 2. 配置 Scope（权限范围）

在管理后台为应用分配所需的 Scope，决定应用可以调用哪些 API：

| Scope | 说明 | 可调用的 API |
|-------|------|-------------|
| `auth:register` | 用户注册 | 邮箱注册、手机注册 |
| `auth:login` | 用户登录 | 登录、OAuth 登录、Token 刷新 |
| `user:read` | 读取用户信息 | 查询用户资料 |
| `user:write` | 修改用户信息 | 修改密码 |
| `role:read` | 读取角色/权限 | 查询用户角色、查询用户权限、权限检查 |
| `role:write` | 管理角色 | 分配角色、移除角色 |

### 3. 配置登录方式

在管理后台启用应用支持的登录方式：`email`、`phone`、`wechat`、`alipay`、`google`、`apple`。

---

## 认证机制

网关使用两种认证方式，根据 API 类型不同：

### 应用凭证认证（App Credential）

用于注册、登录等不需要用户 Token 的端点。通过请求头传递：

```
X-App-Id: your_app_id
X-App-Secret: your_app_secret
```

### Bearer Token 认证

用于需要用户身份的端点（查询用户、角色管理等）。用户登录成功后获得 `access_token`，通过请求头传递：

```
Authorization: Bearer <access_token>
```

> Token 中已包含 `app_id`，网关会自动验证用户是否属于该应用。

---

## 通用响应格式

### 成功响应

每个成功响应都包含 `request_id` 字段，用于问题追踪：

```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"
}
```

### 错误响应

所有错误使用统一格式：

```json
{
  "error_code": "insufficient_scope",
  "message": "应用未被授予所需的权限范围: role:write",
  "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"
}
```

### 错误码一览

| error_code | HTTP 状态码 | 说明 |
|------------|-----------|------|
| `invalid_credentials` | 401 | app_id 或 app_secret 无效 |
| `app_disabled` | 403 | 应用已被禁用 |
| `token_expired` | 401 | access_token 已过期，需刷新 |
| `invalid_token` | 401 | access_token 格式无效或缺少 app_id |
| `login_method_disabled` | 400 | 该登录方式未启用 |
| `insufficient_scope` | 403 | 应用缺少所需的 Scope |
| `user_not_bound` | 403 | 用户不属于该应用 |
| `rate_limit_exceeded` | 429 | 请求频率超限 |
| `service_unavailable` | 503 | 服务暂时不可用 |
| `upstream_error` | 502 | 上游服务异常 |
| `validation_error` | 422 | 请求参数验证失败 |

### 限流响应头

每个响应都包含限流信息：

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 58
X-RateLimit-Reset: 1700000000
```

---

## API 端点详情

### 一、用户注册

#### 1.1 邮箱注册

```
POST /api/v1/gateway/auth/register/email
```

**认证方式**: 应用凭证  
**所需 Scope**: `auth:register`  
**所需登录方式**: `email`

**请求头**:
```
X-App-Id: your_app_id
X-App-Secret: your_app_secret
Content-Type: application/json
```

**请求体**:
```json
{
  "email": "user@example.com",
  "password": "SecurePass123",
  "nickname": "用户昵称"
}
```

**成功响应** (200):
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_id": "..."
}
```

> 注册成功后，平台会自动创建用户与应用的绑定关系，并根据应用的自动配置规则分配角色、权限、组织和订阅。

---

#### 1.2 手机注册

```
POST /api/v1/gateway/auth/register/phone
```

**认证方式**: 应用凭证  
**所需 Scope**: `auth:register`  
**所需登录方式**: `phone`

**请求体**:
```json
{
  "phone": "+8613800138000",
  "verification_code": "123456",
  "password": "SecurePass123"
}
```

---

### 二、用户登录

#### 2.1 账号密码登录

```
POST /api/v1/gateway/auth/login
```

**认证方式**: 应用凭证  
**所需 Scope**: `auth:login`

**请求体**:
```json
{
  "identifier": "user@example.com",
  "password": "SecurePass123"
}
```

> `identifier` 可以是邮箱或手机号，系统自动识别。

**成功响应** (200):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "request_id": "..."
}
```

> 返回的 Token 中已注入 `app_id`，后续使用 Bearer Token 调用其他 API 时，网关会自动验证用户与应用的绑定关系。

---

#### 2.2 OAuth 第三方登录

```
POST /api/v1/gateway/auth/oauth/{provider}
```

**认证方式**: 应用凭证  
**所需 Scope**: `auth:login`  
**所需登录方式**: 对应的 provider（`wechat`/`alipay`/`google`/`apple`）

**路径参数**:
- `provider`: OAuth 提供商名称

**请求体**:
```json
{
  "code": "oauth_authorization_code"
}
```

> 如果应用在管理后台配置了自己的 OAuth Client ID/Secret，网关会自动使用应用级配置替代全局配置。

**成功响应** (200):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "is_new_user": true,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "nickname": "微信用户"
  },
  "request_id": "..."
}
```

---

#### 2.3 Token 刷新

```
POST /api/v1/gateway/auth/refresh
```

**认证方式**: 应用凭证  
**所需 Scope**: `auth:login`

**请求体**:
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**成功响应** (200):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...(新)",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...(新)",
  "token_type": "bearer",
  "request_id": "..."
}
```

---

### 三、用户信息

#### 3.1 查询用户资料

```
GET /api/v1/gateway/users/{user_id}
```

**认证方式**: Bearer Token  
**所需 Scope**: `user:read`

**请求头**:
```
Authorization: Bearer <access_token>
```

---

#### 3.2 修改密码

```
POST /api/v1/gateway/auth/change-password
```

**认证方式**: Bearer Token  
**所需 Scope**: `user:write`

**请求体**:
```json
{
  "old_password": "OldPass123",
  "new_password": "NewPass456"
}
```

---

### 四、角色与权限管理

#### 4.1 查询用户角色

```
GET /api/v1/gateway/users/{user_id}/roles
```

**认证方式**: Bearer Token  
**所需 Scope**: `role:read`

**成功响应** (200):
```json
[
  {
    "role_id": "...",
    "role_name": "editor",
    "role_description": "编辑者",
    "assigned_at": "2025-01-01T00:00:00"
  }
]
```

---

#### 4.2 查询用户所有权限

```
GET /api/v1/gateway/users/{user_id}/permissions
```

**认证方式**: Bearer Token  
**所需 Scope**: `role:read`

**成功响应** (200):
```json
{
  "user_id": "...",
  "permissions": [
    {
      "id": "...",
      "name": "article:edit",
      "resource": "article",
      "action": "edit",
      "source_role": "editor"
    }
  ],
  "request_id": "..."
}
```

---

#### 4.3 检查用户是否拥有某权限

```
POST /api/v1/gateway/users/{user_id}/permissions/check
```

**认证方式**: Bearer Token  
**所需 Scope**: `role:read`

**请求体**:
```json
{
  "permission": "article:edit"
}
```

**成功响应** (200):
```json
{
  "has_permission": true,
  "request_id": "..."
}
```

---

#### 4.4 为用户分配角色

```
POST /api/v1/gateway/users/{user_id}/roles
```

**认证方式**: Bearer Token  
**所需 Scope**: `role:write`

**请求体**:
```json
{
  "role_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
  ]
}
```

**成功响应** (200):
```json
{
  "success": true,
  "message": "成功分配 2 个角色",
  "assigned_count": 2,
  "request_id": "..."
}
```

> 已存在的角色绑定会被跳过（幂等操作），`assigned_count` 只计算新增的绑定数。

---

#### 4.5 移除用户角色

```
DELETE /api/v1/gateway/users/{user_id}/roles/{role_id}
```

**认证方式**: Bearer Token  
**所需 Scope**: `role:write`

**成功响应** (200):
```json
{
  "success": true,
  "message": "角色已移除",
  "request_id": "..."
}
```

---

### 五、辅助端点

#### 5.1 网关信息

```
GET /api/v1/gateway/info
```

**认证方式**: 无需认证

**成功响应** (200):
```json
{
  "version": "1.0.0",
  "supported_api_versions": ["v1"],
  "available_login_methods": ["email", "phone", "wechat", "alipay", "google", "apple"]
}
```

#### 5.2 健康检查

```
GET /health
```

**认证方式**: 无需认证

---

## 对接流程示例

### 典型对接流程

```
1. 管理后台创建应用 → 获得 app_id + app_secret
2. 管理后台配置 Scope（如 auth:register, auth:login, role:read, role:write）
3. 管理后台启用登录方式（如 email, phone）
4. 第三方应用调用注册/登录 API → 获得 access_token
5. 使用 access_token 调用用户/角色/权限 API
6. access_token 过期时，使用 refresh_token 刷新
```

### cURL 示例

**注册用户**:
```bash
curl -X POST http://localhost:8008/api/v1/gateway/auth/register/email \
  -H "X-App-Id: your_app_id" \
  -H "X-App-Secret: your_app_secret" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "SecurePass123"}'
```

**登录**:
```bash
curl -X POST http://localhost:8008/api/v1/gateway/auth/login \
  -H "X-App-Id: your_app_id" \
  -H "X-App-Secret: your_app_secret" \
  -H "Content-Type: application/json" \
  -d '{"identifier": "user@example.com", "password": "SecurePass123"}'
```

**分配角色**:
```bash
curl -X POST http://localhost:8008/api/v1/gateway/users/{user_id}/roles \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"role_ids": ["role_uuid_1", "role_uuid_2"]}'
```

**检查权限**:
```bash
curl -X POST http://localhost:8008/api/v1/gateway/users/{user_id}/permissions/check \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"permission": "article:edit"}'
```

---

## 注意事项

1. **安全**: `app_secret` 只能在服务端使用，禁止在前端代码或客户端中暴露
2. **限流**: 每个应用有独立的请求频率限制（默认 60 次/分钟），可在管理后台调整
3. **用户绑定**: 通过网关注册的用户会自动绑定到对应应用，Bearer Token 端点会验证用户是否属于该应用
4. **Token 有效期**: access_token 有效期较短，过期后使用 refresh_token 刷新，避免频繁登录
5. **幂等性**: 角色分配、用户注册等操作均为幂等操作，重复调用不会产生副作用
6. **自动配置**: 如果应用配置了自动配置规则（Auto Provision），新注册用户会自动获得预设的角色、权限、组织和订阅
