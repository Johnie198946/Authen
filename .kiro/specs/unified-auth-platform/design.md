# 设计文档：统一身份认证和权限管理平台

## 概述

统一身份认证和权限管理平台（Unified Auth Platform）是一个基于微服务架构的企业级IAM系统。该平台采用OAuth 2.0和OpenID Connect（OIDC）协议实现单点登录，使用JWT（JSON Web Token）进行无状态认证，并通过RBAC（基于角色的访问控制）模型管理权限。

### 核心技术栈

**后端技术：**
- 编程语言：Python 3.11+（使用FastAPI框架）
- 数据库：PostgreSQL 14+（关系型数据存储）
- 缓存：Redis 7+（会话、Token缓存）
- 消息队列：RabbitMQ（异步任务处理）
- API文档：OpenAPI 3.0（Swagger UI）

**前端技术：**
- 框架：React 18+（管理后台）
- 状态管理：Redux Toolkit
- UI组件库：Ant Design
- 构建工具：Vite

**基础设施：**
- 容器化：Docker + Docker Compose
- 负载均衡：Nginx
- 监控：Prometheus + Grafana
- 日志：ELK Stack（Elasticsearch + Logstash + Kibana）

### 设计原则

1. **安全第一**：所有通信使用HTTPS，敏感数据加密存储，实施多层安全防护
2. **无状态设计**：使用JWT实现无状态认证，支持水平扩展
3. **模块化架构**：各服务独立部署，松耦合设计
4. **高可用性**：支持负载均衡、故障转移和数据备份
5. **可扩展性**：支持插件式扩展新的认证提供商
6. **用户体验**：简洁直观的管理界面，详细的错误提示

## 架构设计

### 系统架构图

```mermaid
graph TB
    subgraph "客户端层"
        WebApp[Web应用]
        iOSApp[iOS应用]
        AndroidApp[Android应用]
        AdminUI[管理后台]
    end
    
    subgraph "API网关层"
        Gateway[Nginx API Gateway]
        RateLimit[限流模块]
    end
    
    subgraph "服务层"
        AuthService[认证服务]
        SSOService[SSO服务]
        UserService[用户服务]
        PermService[权限服务]
        SubService[订阅服务]
        NotifyService[通知服务]
    end
    
    subgraph "数据层"
        PostgreSQL[(PostgreSQL)]
        Redis[(Redis)]
        RabbitMQ[RabbitMQ]
    end
    
    subgraph "外部服务"
        Email[邮件服务]
        SMS[短信服务]
        WeChat[微信OAuth]
        Alipay[支付宝OAuth]
        Google[Google OAuth]
        Apple[Apple OAuth]
    end
    
    WebApp --> Gateway
    iOSApp --> Gateway
    AndroidApp --> Gateway
    AdminUI --> Gateway
    
    Gateway --> RateLimit
    RateLimit --> AuthService
    RateLimit --> SSOService
    RateLimit --> UserService
    RateLimit --> PermService
    RateLimit --> SubService
    
    AuthService --> PostgreSQL
    AuthService --> Redis
    AuthService --> WeChat
    AuthService --> Alipay
    AuthService --> Google
    AuthService --> Apple
    
    SSOService --> Redis
    SSOService --> PostgreSQL
    
    UserService --> PostgreSQL
    UserService --> Redis
    
    PermService --> PostgreSQL
    PermService --> Redis
    
    SubService --> PostgreSQL
    SubService --> RabbitMQ
    
    NotifyService --> RabbitMQ
    NotifyService --> Email
    NotifyService --> SMS
```

### 服务职责划分

**1. 认证服务（Auth Service）**
- 处理用户注册（邮箱、手机、第三方OAuth）
- 验证用户凭证（密码、验证码）
- 生成和验证JWT Token
- 管理Refresh Token
- 实现账号锁定机制

**2. SSO服务（SSO Service）**
- 实现OAuth 2.0授权服务器
- 实现OpenID Connect身份提供商
- 管理全局会话
- 处理跨应用认证
- 实现统一登出

**3. 用户服务（User Service）**
- 用户信息CRUD操作
- 用户资料管理
- 用户搜索和查询
- 用户状态管理

**4. 权限服务（Permission Service）**
- RBAC权限模型实现
- 角色和权限管理
- 组织架构树管理
- 权限验证和检查
- 权限继承计算

**5. 订阅服务（Subscription Service）**
- 订阅计划管理
- 用户订阅状态跟踪
- 订阅到期处理
- 订阅通知

**6. 通知服务（Notification Service）**
- 邮件发送（验证邮件、通知邮件）
- 短信发送（验证码、通知短信）
- 消息模板管理
- 异步消息处理

## 组件和接口

### 数据模型

#### 用户表（users）

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(20) UNIQUE,
    password_hash VARCHAR(255),
    status VARCHAR(20) DEFAULT 'active', -- active, locked, disabled
    failed_login_attempts INT DEFAULT 0,
    locked_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP,
    CONSTRAINT check_auth_method CHECK (
        email IS NOT NULL OR phone IS NOT NULL
    )
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_phone ON users(phone);
CREATE INDEX idx_users_status ON users(status);
```

#### 第三方认证表（oauth_accounts）

```sql
CREATE TABLE oauth_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL, -- wechat, alipay, google, apple
    provider_user_id VARCHAR(255) NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, provider_user_id)
);

CREATE INDEX idx_oauth_user_id ON oauth_accounts(user_id);
CREATE INDEX idx_oauth_provider ON oauth_accounts(provider, provider_user_id);
```

#### 角色表（roles）

```sql
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    is_system_role BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_roles_name ON roles(name);
```

#### 权限表（permissions）

```sql
CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    resource VARCHAR(100) NOT NULL, -- 资源类型，如 user, role, subscription
    action VARCHAR(50) NOT NULL, -- 操作类型，如 create, read, update, delete
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_permissions_resource ON permissions(resource, action);
```

#### 角色权限关联表（role_permissions）

```sql
CREATE TABLE role_permissions (
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (role_id, permission_id)
);
```

#### 用户角色关联表（user_roles）

```sql
CREATE TABLE user_roles (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id)
);
```

#### 组织架构表（organizations）

```sql
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    parent_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    path TEXT NOT NULL, -- 存储完整路径，如 /root/dept1/team1
    level INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_org_parent ON organizations(parent_id);
CREATE INDEX idx_org_path ON organizations(path);
```

#### 用户组织关联表（user_organizations）

```sql
CREATE TABLE user_organizations (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, organization_id)
);
```

#### 组织权限表（organization_permissions）

```sql
CREATE TABLE organization_permissions (
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (organization_id, permission_id)
);
```

#### 订阅计划表（subscription_plans）

```sql
CREATE TABLE subscription_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    duration_days INT NOT NULL, -- 订阅周期（天）
    price DECIMAL(10, 2) NOT NULL,
    features JSONB, -- 订阅包含的功能特性
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 用户订阅表（user_subscriptions）

```sql
CREATE TABLE user_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES subscription_plans(id),
    status VARCHAR(20) DEFAULT 'active', -- active, expired, cancelled
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    auto_renew BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sub_user ON user_subscriptions(user_id);
CREATE INDEX idx_sub_status ON user_subscriptions(status);
CREATE INDEX idx_sub_end_date ON user_subscriptions(end_date);
```

#### Refresh Token表（refresh_tokens）

```sql
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP
);

CREATE INDEX idx_refresh_token_hash ON refresh_tokens(token_hash);
CREATE INDEX idx_refresh_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_expires ON refresh_tokens(expires_at);
```

#### SSO会话表（sso_sessions）

```sql
CREATE TABLE sso_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sso_session_token ON sso_sessions(session_token);
CREATE INDEX idx_sso_user_id ON sso_sessions(user_id);
```

#### 审计日志表（audit_logs）

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL, -- login, logout, create_user, update_role, etc.
    resource_type VARCHAR(50), -- user, role, permission, etc.
    resource_id UUID,
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_created ON audit_logs(created_at);
```

#### 云服务配置表（cloud_service_configs）

```sql
CREATE TABLE cloud_service_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_type VARCHAR(50) NOT NULL, -- email, sms
    provider VARCHAR(50) NOT NULL, -- aliyun, tencent, aws
    config JSONB NOT NULL, -- 加密存储的配置信息
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(service_type, provider)
);
```

#### 消息模板表（message_templates）

```sql
CREATE TABLE message_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    type VARCHAR(20) NOT NULL, -- email, sms
    subject VARCHAR(255), -- 仅用于邮件
    content TEXT NOT NULL,
    variables JSONB, -- 模板变量说明
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### API接口设计

#### 认证相关接口

**POST /api/v1/auth/register/email**
```json
请求：
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "username": "johndoe"
}

响应：
{
  "success": true,
  "message": "验证邮件已发送，请查收",
  "user_id": "uuid"
}
```

**POST /api/v1/auth/register/phone**
```json
请求：
{
  "phone": "+86138****1234",
  "password": "SecurePass123!",
  "username": "johndoe",
  "verification_code": "123456"
}

响应：
{
  "success": true,
  "message": "注册成功",
  "user_id": "uuid"
}
```

**POST /api/v1/auth/login**
```json
请求：
{
  "identifier": "user@example.com", // 邮箱或手机号
  "password": "SecurePass123!"
}

响应：
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 900, // 15分钟
  "user": {
    "id": "uuid",
    "username": "johndoe",
    "email": "user@example.com"
  }
}
```

**POST /api/v1/auth/oauth/{provider}**
```json
请求：
{
  "code": "oauth_authorization_code",
  "redirect_uri": "https://app.example.com/callback"
}

响应：
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid",
    "username": "johndoe",
    "email": "user@example.com"
  }
}
```

**POST /api/v1/auth/refresh**
```json
请求：
{
  "refresh_token": "eyJhbGc..."
}

响应：
{
  "access_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 900
}
```

**POST /api/v1/auth/logout**
```json
请求头：
Authorization: Bearer eyJhbGc...

响应：
{
  "success": true,
  "message": "登出成功"
}
```

#### SSO相关接口

**GET /api/v1/sso/authorize**
```
查询参数：
- client_id: 客户端应用ID
- redirect_uri: 回调地址
- response_type: code
- scope: openid profile email
- state: 随机状态值

响应：重定向到登录页面或返回授权码
```

**POST /api/v1/sso/token**
```json
请求：
{
  "grant_type": "authorization_code",
  "code": "authorization_code",
  "client_id": "client_id",
  "client_secret": "client_secret",
  "redirect_uri": "https://app.example.com/callback"
}

响应：
{
  "access_token": "eyJhbGc...",
  "id_token": "eyJhbGc...", // OpenID Connect ID Token
  "token_type": "Bearer",
  "expires_in": 900
}
```

**GET /api/v1/sso/userinfo**
```json
请求头：
Authorization: Bearer eyJhbGc...

响应：
{
  "sub": "user_id",
  "name": "John Doe",
  "email": "user@example.com",
  "email_verified": true
}
```

**POST /api/v1/sso/logout**
```json
请求：
{
  "session_token": "session_token"
}

响应：
{
  "success": true,
  "message": "全局登出成功"
}
```

#### 用户管理接口

**GET /api/v1/users**
```
查询参数：
- page: 页码
- page_size: 每页数量
- search: 搜索关键词
- status: 用户状态过滤

响应：
{
  "total": 100,
  "page": 1,
  "page_size": 20,
  "users": [...]
}
```

**GET /api/v1/users/{user_id}**
**PUT /api/v1/users/{user_id}**
**DELETE /api/v1/users/{user_id}**

#### 权限管理接口

**GET /api/v1/roles**
**POST /api/v1/roles**
**PUT /api/v1/roles/{role_id}**
**DELETE /api/v1/roles/{role_id}**

**GET /api/v1/permissions**
**POST /api/v1/permissions**

**POST /api/v1/roles/{role_id}/permissions**
```json
请求：
{
  "permission_ids": ["uuid1", "uuid2"]
}
```

**POST /api/v1/users/{user_id}/roles**
```json
请求：
{
  "role_ids": ["uuid1", "uuid2"]
}
```

**GET /api/v1/users/{user_id}/permissions**
```json
响应：
{
  "permissions": [
    {
      "id": "uuid",
      "name": "user:create",
      "resource": "user",
      "action": "create",
      "source": "role" // 或 "organization"
    }
  ]
}
```

#### 组织架构接口

**GET /api/v1/organizations/tree**
```json
响应：
{
  "id": "root_uuid",
  "name": "根组织",
  "children": [
    {
      "id": "dept1_uuid",
      "name": "部门1",
      "children": [...]
    }
  ]
}
```

**POST /api/v1/organizations**
**PUT /api/v1/organizations/{org_id}**
**DELETE /api/v1/organizations/{org_id}**

**POST /api/v1/organizations/{org_id}/users**
```json
请求：
{
  "user_ids": ["uuid1", "uuid2"]
}
```

**POST /api/v1/organizations/{org_id}/permissions**
```json
请求：
{
  "permission_ids": ["uuid1", "uuid2"]
}
```

#### 订阅管理接口

**GET /api/v1/subscriptions/plans**
**POST /api/v1/subscriptions/plans**
**PUT /api/v1/subscriptions/plans/{plan_id}**

**GET /api/v1/users/{user_id}/subscription**
**POST /api/v1/users/{user_id}/subscription**
```json
请求：
{
  "plan_id": "uuid",
  "auto_renew": true
}
```

**DELETE /api/v1/users/{user_id}/subscription**

#### 云服务配置接口

**GET /api/v1/admin/cloud-services**
**POST /api/v1/admin/cloud-services**
```json
请求：
{
  "service_type": "email",
  "provider": "aliyun",
  "config": {
    "smtp_host": "smtp.aliyun.com",
    "smtp_port": 465,
    "username": "noreply@example.com",
    "password": "encrypted_password",
    "use_ssl": true
  }
}
```

**PUT /api/v1/admin/cloud-services/{config_id}**
**POST /api/v1/admin/cloud-services/{config_id}/test**

#### 消息模板接口

**GET /api/v1/admin/templates**
**POST /api/v1/admin/templates**
**PUT /api/v1/admin/templates/{template_id}**

#### 审计日志接口

**GET /api/v1/admin/audit-logs**
```
查询参数：
- user_id: 用户ID过滤
- action: 操作类型过滤
- start_date: 开始日期
- end_date: 结束日期
- page: 页码
- page_size: 每页数量
```

### JWT Token设计

#### Access Token结构

```json
{
  "header": {
    "alg": "RS256",
    "typ": "JWT"
  },
  "payload": {
    "sub": "user_id",
    "username": "johndoe",
    "email": "user@example.com",
    "roles": ["user", "admin"],
    "permissions": ["user:read", "user:create"],
    "iat": 1234567890,
    "exp": 1234568790, // 15分钟后过期
    "iss": "unified-auth-platform",
    "aud": "client_app_id"
  }
}
```

#### Refresh Token结构

```json
{
  "header": {
    "alg": "RS256",
    "typ": "JWT"
  },
  "payload": {
    "sub": "user_id",
    "token_id": "refresh_token_uuid",
    "iat": 1234567890,
    "exp": 1235777890, // 14天后过期
    "iss": "unified-auth-platform"
  }
}
```

#### Token安全策略

1. **Access Token**：
   - 有效期：15分钟
   - 算法：RS256（非对称加密）
   - 存储：客户端内存（不存储在localStorage）
   - 传输：HTTP Authorization头

2. **Refresh Token**：
   - 有效期：14天（绝对过期，不延长）
   - 存储：HttpOnly + Secure Cookie
   - 轮换策略：每次刷新时生成新的Refresh Token
   - 数据库记录：存储Token哈希值，支持撤销

3. **Token撤销**：
   - 登出时撤销Refresh Token
   - 密码修改时撤销所有Token
   - 检测到异常时撤销Token

### 认证流程

#### 邮箱注册流程

```mermaid
sequenceDiagram
    participant User
    participant Client
    participant AuthService
    participant NotifyService
    participant Database
    
    User->>Client: 输入邮箱和密码
    Client->>AuthService: POST /auth/register/email
    AuthService->>Database: 检查邮箱是否已存在
    Database-->>AuthService: 邮箱可用
    AuthService->>Database: 创建用户（状态：未验证）
    AuthService->>NotifyService: 发送验证邮件
    NotifyService-->>User: 验证邮件
    AuthService-->>Client: 注册成功，等待验证
    User->>Client: 点击验证链接
    Client->>AuthService: GET /auth/verify-email?token=xxx
    AuthService->>Database: 更新用户状态为已验证
    AuthService-->>Client: 验证成功
```

#### OAuth登录流程

```mermaid
sequenceDiagram
    participant User
    participant Client
    participant AuthService
    participant OAuthProvider
    participant Database
    
    User->>Client: 点击第三方登录
    Client->>AuthService: GET /auth/oauth/{provider}
    AuthService-->>Client: 重定向到OAuth提供商
    Client->>OAuthProvider: 授权请求
    User->>OAuthProvider: 授权
    OAuthProvider-->>Client: 返回授权码
    Client->>AuthService: POST /auth/oauth/{provider} + code
    AuthService->>OAuthProvider: 交换Access Token
    OAuthProvider-->>AuthService: Access Token
    AuthService->>OAuthProvider: 获取用户信息
    OAuthProvider-->>AuthService: 用户信息
    AuthService->>Database: 查找或创建用户
    AuthService->>Database: 创建Refresh Token
    AuthService-->>Client: JWT Token
```

#### SSO单点登录流程

```mermaid
sequenceDiagram
    participant User
    participant App1
    participant App2
    participant SSOService
    participant Database
    
    User->>App1: 访问应用1
    App1->>SSOService: 检查SSO会话
    SSOService-->>App1: 无会话
    App1-->>User: 重定向到登录页
    User->>SSOService: 登录
    SSOService->>Database: 验证凭证
    SSOService->>Database: 创建SSO会话
    SSOService-->>App1: 返回授权码
    App1->>SSOService: 交换Token
    SSOService-->>App1: Access Token
    App1-->>User: 登录成功
    
    User->>App2: 访问应用2
    App2->>SSOService: 检查SSO会话
    SSOService->>Database: 查询会话
    SSOService-->>App2: 会话有效
    App2->>SSOService: 请求Token
    SSOService-->>App2: Access Token
    App2-->>User: 自动登录成功
```

### 权限验证流程

```mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant PermService
    participant Redis
    participant Database
    
    Client->>Gateway: API请求 + JWT
    Gateway->>Gateway: 验证JWT签名
    Gateway->>PermService: 检查权限
    PermService->>Redis: 查询缓存的权限
    alt 缓存命中
        Redis-->>PermService: 返回权限列表
    else 缓存未命中
        PermService->>Database: 查询用户角色
        PermService->>Database: 查询角色权限
        PermService->>Database: 查询组织权限
        PermService->>PermService: 合并权限
        PermService->>Redis: 缓存权限（TTL: 5分钟）
    end
    PermService->>PermService: 验证所需权限
    alt 有权限
        PermService-->>Gateway: 授权通过
        Gateway->>Gateway: 转发请求
    else 无权限
        PermService-->>Gateway: 授权失败
        Gateway-->>Client: 403 Forbidden
    end
```



## 正确性属性

*属性是一个特征或行为，应该在系统的所有有效执行中保持为真——本质上是关于系统应该做什么的形式化陈述。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。*

### 属性 1：邮箱注册完整性

*对于任意*有效的邮箱地址和密码，当用户通过邮箱注册时，系统应该发送验证邮件，并在用户点击验证链接后成功创建账号且账号状态为已验证。

**验证需求：1.1**

### 属性 2：手机注册完整性

*对于任意*有效的手机号和密码，当用户通过手机注册并提供正确的验证码时，系统应该成功创建账号且账号状态为已验证。

**验证需求：1.2**

### 属性 3：OAuth认证账号关联

*对于任意*OAuth提供商（微信、支付宝、Google、Apple），当用户通过OAuth认证时，系统应该正确创建新账号或关联到现有账号，并返回有效的JWT Token。

**验证需求：1.3**

### 属性 4：登录Token生成

*对于任意*认证方式（邮箱、手机、OAuth），当用户成功登录时，系统应该返回有效的Access Token和Refresh Token，且两个Token都能通过签名验证。

**验证需求：1.4**

### 属性 5：Token刷新往返

*对于任意*有效的Refresh Token，当Access Token过期后使用Refresh Token刷新时，系统应该返回新的Access Token，且新Token能够成功验证用户身份。

**验证需求：1.5**

### 属性 6：账号锁定机制

*对于任意*用户账号，当连续输入错误密码5次后，账号应该被锁定15分钟，在锁定期间任何登录尝试都应该被拒绝。

**验证需求：1.6**

### 属性 7：密码加密存储

*对于任意*用户密码，存储到数据库中的值应该是经过bcrypt或类似算法加密的哈希值，且原始密码不应该能从哈希值中恢复。

**验证需求：1.7**

### 属性 8：SSO全局会话创建

*对于任意*客户端应用，当用户在该应用中成功登录时，系统应该创建一个全局SSO会话，且该会话可以被其他应用查询到。

**验证需求：2.1**

### 属性 9：SSO自动认证

*对于任意*两个客户端应用A和B，当用户在应用A登录后访问应用B时，应用B应该能够通过SSO会话自动完成认证，无需用户再次输入凭证。

**验证需求：2.2**

### 属性 10：SSO全局登出

*对于任意*客户端应用，当用户在该应用中登出时，系统应该终止全局SSO会话，且所有其他应用的会话也应该失效。

**验证需求：2.3**

### 属性 11：SSO身份验证响应

*对于任意*有效的SSO会话，当客户端应用请求验证用户身份时，系统应该返回用户的认证状态和基本信息（用户ID、用户名、邮箱）。

**验证需求：2.4**

### 属性 12：订阅购买完整性

*对于任意*用户和订阅计划，当用户购买订阅时，系统应该正确记录订阅信息（开始日期、结束日期、计划ID），并且用户的订阅状态应该变为active。

**验证需求：3.1**

### 属性 13：订阅到期权限降级

*对于任意*已到期的订阅，系统应该自动将订阅状态更新为expired，且用户不应该再拥有该订阅计划提供的权益。

**验证需求：3.2**

### 属性 14：订阅取消处理

*对于任意*活跃订阅，当用户取消订阅时，系统应该将auto_renew标记为false，且订阅应该在当前周期结束后自动过期。

**验证需求：3.3**

### 属性 15：订阅状态查询

*对于任意*用户，查询其订阅状态时，系统应该返回正确的订阅级别、到期时间和自动续费状态。

**验证需求：3.5**

### 属性 16：订阅到期提醒

*对于任意*将在7天内到期的订阅，系统应该发送提醒通知给用户。

**验证需求：3.6**

### 属性 17：角色权限分配

*对于任意*角色和权限集合，当管理员为角色分配权限时，系统应该正确创建角色-权限关联关系，且该角色应该包含所有分配的权限。

**验证需求：4.2**

### 属性 18：用户角色权限继承

*对于任意*用户和角色，当管理员为用户分配角色时，用户应该自动获得该角色的所有权限。

**验证需求：4.3**

### 属性 19：权限验证正确性

*对于任意*用户和资源访问请求，系统应该正确验证用户是否拥有所需权限，有权限时允许访问，无权限时拒绝访问。

**验证需求：4.4**

### 属性 20：角色权限更新即时生效

*对于任意*角色，当管理员修改该角色的权限时，所有拥有该角色的用户的权限应该立即更新（通过缓存失效机制）。

**验证需求：4.5**

### 属性 21：组织节点父子关系

*对于任意*组织节点，当创建时指定父节点，系统应该正确建立父子关系，且节点的path字段应该包含从根节点到当前节点的完整路径。

**验证需求：5.2**

### 属性 22：用户组织归属

*对于任意*用户和组织节点，当管理员将用户分配到组织时，系统应该正确记录用户的组织归属关系。

**验证需求：5.3**

### 属性 23：组织权限继承

*对于任意*组织节点，当管理员为该节点设置权限时，该节点及其所有子节点的用户都应该继承这些权限。

**验证需求：5.4**

### 属性 24：组织移动权限更新

*对于任意*组织节点，当管理员将其移动到新的父节点下时，该节点及其子节点的所有用户的权限应该根据新的继承关系重新计算。

**验证需求：5.5**

### 属性 25：超级管理员无限权限

*对于*超级管理员账号，执行任何操作时都应该跳过权限检查，且所有操作都应该成功（除非是系统错误）。

**验证需求：6.2, 6.3**

### 属性 26：超级管理员创建管理员

*对于*超级管理员，应该能够成功创建其他管理员账号，且新创建的管理员应该拥有管理员角色。

**验证需求：6.4**

### 属性 27：云服务配置验证

*对于任意*云服务配置（邮件或短信），当管理员保存配置时，系统应该验证配置的有效性（如SMTP连接、API密钥有效性），无效配置应该被拒绝。

**验证需求：8.5**

### 属性 28：API请求限流

*对于任意*客户端，当在短时间内发送大量请求时，系统应该触发限流机制，返回429 Too Many Requests错误。

**验证需求：9.7**

### 属性 29：CSRF攻击防护

*对于任意*状态改变的API请求（POST、PUT、DELETE），如果请求缺少有效的CSRF Token，系统应该拒绝该请求。

**验证需求：11.2**

### 属性 30：SQL注入防护

*对于任意*包含SQL注入攻击载荷的输入，系统应该正确转义或参数化查询，不应该执行恶意SQL语句。

**验证需求：11.3**

### 属性 31：XSS攻击防护

*对于任意*包含XSS攻击载荷的输入，系统应该正确转义或清理输入，返回的HTML内容不应该执行恶意脚本。

**验证需求：11.4**

### 属性 32：异常登录检测

*对于任意*用户，当检测到异常登录行为（如异地登录、设备变更）时，系统应该发送安全警告通知给用户。

**验证需求：11.5**

### 属性 33：过期数据清理

*对于任意*过期的Token或会话数据，系统的定期清理任务应该能够识别并删除这些数据。

**验证需求：11.7**

### 属性 34：用户数据导出

*对于任意*用户，当请求导出个人数据时，系统应该返回该用户的所有相关数据（用户信息、订阅记录、操作日志等）的完整副本。

**验证需求：11.8**

### 属性 35：综合审计日志记录

*对于任意*敏感操作（用户认证、管理操作、权限变更、超级管理员操作），系统应该记录详细的审计日志，包括操作者、操作类型、操作时间、IP地址和操作详情。

**验证需求：6.5, 9.8, 11.9, 13.1, 13.2**

## 错误处理

### 错误分类

系统将错误分为以下几类：

1. **客户端错误（4xx）**
   - 400 Bad Request：请求参数无效
   - 401 Unauthorized：未认证或Token无效
   - 403 Forbidden：无权限访问
   - 404 Not Found：资源不存在
   - 409 Conflict：资源冲突（如邮箱已存在）
   - 422 Unprocessable Entity：业务逻辑验证失败
   - 429 Too Many Requests：请求过于频繁

2. **服务器错误（5xx）**
   - 500 Internal Server Error：服务器内部错误
   - 502 Bad Gateway：上游服务错误
   - 503 Service Unavailable：服务暂时不可用

### 错误响应格式

所有API错误响应使用统一格式：

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "人类可读的错误消息",
    "details": {
      "field": "具体字段错误信息"
    },
    "request_id": "唯一请求ID，用于追踪"
  }
}
```

### 错误码定义

**认证相关错误：**
- `AUTH_001`：邮箱或手机号已存在
- `AUTH_002`：验证码无效或已过期
- `AUTH_003`：用户名或密码错误
- `AUTH_004`：账号已被锁定
- `AUTH_005`：Token无效或已过期
- `AUTH_006`：Refresh Token无效或已撤销
- `AUTH_007`：OAuth认证失败

**权限相关错误：**
- `PERM_001`：无权限访问该资源
- `PERM_002`：角色不存在
- `PERM_003`：权限不存在
- `PERM_004`：无法删除系统角色

**订阅相关错误：**
- `SUB_001`：订阅计划不存在
- `SUB_002`：订阅已存在
- `SUB_003`：订阅已过期

**组织相关错误：**
- `ORG_001`：组织节点不存在
- `ORG_002`：无法删除有子节点的组织
- `ORG_003`：组织层级超过限制

**通用错误：**
- `GEN_001`：请求参数验证失败
- `GEN_002`：资源不存在
- `GEN_003`：数据库操作失败
- `GEN_004`：外部服务调用失败

### 错误处理策略

1. **输入验证**：
   - 所有API输入使用Pydantic模型验证
   - 验证失败返回422错误，包含详细的字段错误信息
   - 特殊字符转义，防止注入攻击

2. **认证失败**：
   - 密码错误：记录失败次数，5次后锁定账号
   - Token过期：返回401，客户端应使用Refresh Token刷新
   - Token无效：返回401，客户端应重新登录

3. **权限不足**：
   - 返回403错误
   - 记录未授权访问尝试到审计日志
   - 不泄露资源是否存在的信息

4. **资源冲突**：
   - 返回409错误
   - 提供清晰的冲突原因
   - 建议解决方案

5. **外部服务失败**：
   - 邮件/短信发送失败：重试3次，失败后记录到消息队列
   - OAuth服务失败：返回友好的错误消息，建议用户稍后重试
   - 数据库连接失败：使用连接池重试，超时后返回503

6. **事务回滚**：
   - 所有数据库操作使用事务
   - 操作失败时自动回滚
   - 记录错误日志用于排查

7. **优雅降级**：
   - 缓存服务不可用：直接查询数据库
   - 消息队列不可用：同步发送通知
   - 监控服务不可用：继续处理业务请求

### 错误日志记录

所有错误都应该记录到日志系统，包含：
- 错误时间
- 错误类型和错误码
- 请求ID
- 用户ID（如果已认证）
- 请求路径和方法
- 错误堆栈（仅服务器错误）
- 上下文信息

## 测试策略

### 测试方法论

系统采用双重测试策略，结合单元测试和基于属性的测试（Property-Based Testing）：

**单元测试**：
- 验证特定的示例和边界情况
- 测试错误处理逻辑
- 测试集成点和外部服务交互
- 使用pytest框架

**基于属性的测试**：
- 验证跨所有输入的通用属性
- 通过随机化实现全面的输入覆盖
- 每个属性测试运行至少100次迭代
- 使用Hypothesis库

两种测试方法是互补的：单元测试捕获具体的错误，属性测试验证通用的正确性。

### 测试配置

**属性测试配置：**
```python
from hypothesis import settings, HealthCheck

# 全局配置
settings.register_profile("default", 
    max_examples=100,  # 每个属性测试至少100次迭代
    deadline=None,  # 禁用超时限制
    suppress_health_check=[HealthCheck.too_slow]
)
```

**测试标记：**
每个属性测试必须使用注释标记其对应的设计文档属性：

```python
@given(email=emails(), password=passwords())
def test_email_registration_integrity(email, password):
    """
    Feature: unified-auth-platform, Property 1: 邮箱注册完整性
    
    对于任意有效的邮箱地址和密码，当用户通过邮箱注册时，
    系统应该发送验证邮件，并在用户点击验证链接后成功创建账号。
    """
    # 测试实现
```

### 测试覆盖范围

**认证服务测试：**
- 属性测试：邮箱注册、手机注册、OAuth认证、Token生成和刷新、账号锁定
- 单元测试：验证码生成、密码加密、Token签名验证
- 集成测试：与OAuth提供商的交互

**SSO服务测试：**
- 属性测试：全局会话创建、自动认证、全局登出
- 单元测试：授权码生成、ID Token生成
- 集成测试：多应用SSO流程

**权限服务测试：**
- 属性测试：角色权限分配、用户权限继承、权限验证、组织权限继承
- 单元测试：权限计算算法、缓存失效
- 集成测试：复杂权限场景

**订阅服务测试：**
- 属性测试：订阅购买、到期处理、状态查询
- 单元测试：订阅计算逻辑、通知触发
- 集成测试：订阅生命周期

**安全测试：**
- 属性测试：CSRF防护、SQL注入防护、XSS防护、限流机制
- 单元测试：输入验证、输出转义
- 渗透测试：使用OWASP ZAP进行安全扫描

### 测试数据生成

使用Hypothesis生成测试数据：

```python
from hypothesis import strategies as st

# 邮箱生成器
emails = st.emails()

# 手机号生成器（中国）
phone_numbers = st.from_regex(r'^\+86\d{11}$')

# 密码生成器（符合复杂度要求）
passwords = st.text(
    alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters='!@#$%^&*()'
    ),
    min_size=8,
    max_size=32
)

# 用户名生成器
usernames = st.text(
    alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')),
    min_size=3,
    max_size=50
)

# UUID生成器
uuids = st.uuids()

# 组织树生成器
def organization_trees(max_depth=5):
    return st.recursive(
        st.builds(dict, name=st.text(), id=st.uuids()),
        lambda children: st.builds(
            dict,
            name=st.text(),
            id=st.uuids(),
            children=st.lists(children, max_size=3)
        ),
        max_leaves=10
    )
```

### 测试环境

**开发环境：**
- 使用Docker Compose启动所有服务
- 使用测试数据库（PostgreSQL）
- 使用测试Redis实例
- Mock外部服务（OAuth、邮件、短信）

**CI/CD环境：**
- GitHub Actions自动运行测试
- 每次提交触发单元测试和属性测试
- 代码覆盖率要求：>80%
- 测试失败阻止合并

**性能测试环境：**
- 使用Locust进行负载测试
- 模拟1000并发用户
- 监控响应时间和错误率
- 目标：P95响应时间<500ms

### 测试最佳实践

1. **隔离性**：每个测试独立运行，不依赖其他测试
2. **可重复性**：测试结果应该是确定的和可重复的
3. **快速反馈**：单元测试应该在秒级完成
4. **清晰命名**：测试名称应该清楚描述测试内容
5. **最小化Mock**：优先使用真实依赖，必要时才Mock
6. **边界测试**：测试边界条件和极端情况
7. **错误路径**：测试错误处理和异常情况

## 部署架构

### 容器化部署

所有服务使用Docker容器化部署：

```yaml
# docker-compose.yml
version: '3.8'

services:
  # API网关
  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - auth-service
      - sso-service
      - user-service
      - permission-service
      - subscription-service

  # 认证服务
  auth-service:
    build: ./services/auth
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/auth
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis

  # SSO服务
  sso-service:
    build: ./services/sso
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/auth
      - REDIS_URL=redis://redis:6379/1
    depends_on:
      - postgres
      - redis

  # 用户服务
  user-service:
    build: ./services/user
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/auth
      - REDIS_URL=redis://redis:6379/2
    depends_on:
      - postgres
      - redis

  # 权限服务
  permission-service:
    build: ./services/permission
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/auth
      - REDIS_URL=redis://redis:6379/3
    depends_on:
      - postgres
      - redis

  # 订阅服务
  subscription-service:
    build: ./services/subscription
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/auth
      - RABBITMQ_URL=amqp://rabbitmq:5672
    depends_on:
      - postgres
      - rabbitmq

  # 通知服务
  notification-service:
    build: ./services/notification
    environment:
      - RABBITMQ_URL=amqp://rabbitmq:5672
    depends_on:
      - rabbitmq

  # 管理后台
  admin-ui:
    build: ./admin-ui
    ports:
      - "3000:80"

  # PostgreSQL数据库
  postgres:
    image: postgres:14-alpine
    environment:
      - POSTGRES_DB=auth
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres-data:/var/lib/postgresql/data

  # Redis缓存
  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data

  # RabbitMQ消息队列
  rabbitmq:
    image: rabbitmq:3-management-alpine
    ports:
      - "15672:15672"
    volumes:
      - rabbitmq-data:/var/lib/rabbitmq

volumes:
  postgres-data:
  redis-data:
  rabbitmq-data:
```

### 生产环境部署

**基础设施：**
- 云平台：阿里云/腾讯云/AWS
- 容器编排：Kubernetes
- 负载均衡：云负载均衡器（SLB/CLB/ALB）
- 数据库：云数据库RDS（PostgreSQL）
- 缓存：云缓存Redis
- 对象存储：OSS/COS/S3（存储日志和备份）

**高可用配置：**
- 每个服务至少3个副本
- 跨可用区部署
- 数据库主从复制
- Redis哨兵模式
- 自动故障转移

**监控和告警：**
- Prometheus采集指标
- Grafana可视化监控
- AlertManager告警通知
- ELK Stack日志聚合
- 分布式追踪（Jaeger）

**安全加固：**
- 所有通信使用TLS 1.3
- 数据库加密存储
- 定期安全扫描
- WAF防护
- DDoS防护

### 扩展策略

**水平扩展：**
- 无状态服务设计，支持任意扩展
- 使用Kubernetes HPA自动扩展
- 基于CPU和内存使用率触发扩展

**数据库扩展：**
- 读写分离（主库写，从库读）
- 分库分表（按用户ID哈希）
- 连接池管理

**缓存策略：**
- 热点数据缓存（用户信息、权限）
- 缓存预热
- 缓存穿透防护（布隆过滤器）
- 缓存雪崩防护（随机过期时间）

## 技术决策记录

### 为什么选择FastAPI？

- 高性能：基于Starlette和Pydantic，性能接近Node.js和Go
- 类型安全：原生支持Python类型提示
- 自动文档：自动生成OpenAPI文档
- 异步支持：原生支持async/await
- 易于测试：内置测试客户端

### 为什么选择PostgreSQL？

- 成熟稳定：久经考验的关系型数据库
- ACID保证：强一致性事务支持
- JSON支持：原生支持JSONB类型
- 全文搜索：内置全文搜索功能
- 扩展性：支持多种扩展（如PostGIS）

### 为什么选择Redis？

- 高性能：内存存储，读写速度快
- 数据结构丰富：支持String、Hash、List、Set等
- 持久化：支持RDB和AOF持久化
- 分布式：支持集群和哨兵模式
- 广泛应用：成熟的缓存解决方案

### 为什么选择JWT？

- 无状态：不需要服务器端存储会话
- 跨域支持：适合分布式系统
- 标准化：RFC 7519标准
- 自包含：Token包含所有必要信息
- 可扩展：支持自定义Claims

### 为什么选择OAuth 2.0和OIDC？

- 行业标准：广泛采用的认证授权协议
- 安全性：经过充分验证的安全模型
- 灵活性：支持多种授权流程
- 互操作性：与主流OAuth提供商兼容
- 生态系统：丰富的库和工具支持

### 为什么选择RBAC？

- 简单直观：基于角色的权限管理易于理解
- 可扩展：支持权限继承和组织架构
- 性能好：权限检查效率高
- 标准化：NIST标准模型
- 适用性广：适合大多数企业场景

