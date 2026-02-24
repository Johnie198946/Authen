# 统一身份认证和权限管理平台 - 部署和使用指南

## 📋 目录

1. [系统要求](#系统要求)
2. [快速开始](#快速开始)
3. [环境配置](#环境配置)
4. [数据库初始化](#数据库初始化)
5. [服务启动](#服务启动)
6. [系统初始化](#系统初始化)
7. [API使用示例](#api使用示例)
8. [测试验证](#测试验证)
9. [常见问题](#常见问题)

---

## 系统要求

### 必需软件
- **Docker**: >= 20.10
- **Docker Compose**: >= 2.0
- **Python**: >= 3.12 (如果本地运行)
- **PostgreSQL**: >= 14 (Docker中已包含)
- **Redis**: >= 7 (Docker中已包含)
- **RabbitMQ**: >= 3.12 (Docker中已包含)

### 硬件要求
- **CPU**: 2核心以上
- **内存**: 4GB以上
- **磁盘**: 10GB可用空间

---

## 快速开始

### 1. 克隆项目（如果还没有）
```bash
# 如果项目已在本地，跳过此步骤
cd /path/to/unified-auth-platform
```

### 2. 生成RSA密钥对
```bash
python scripts/generate_keys.py
```

这将在项目根目录生成：
- `private_key.pem` - JWT签名私钥
- `public_key.pem` - JWT验证公钥

### 3. 配置环境变量
```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必要的环境变量（见下方详细说明）。

### 4. 启动所有服务
```bash
docker-compose up -d
```

### 5. 初始化数据库
```bash
# 等待数据库启动（约10秒）
sleep 10

# 运行数据库迁移
docker-compose exec auth alembic upgrade head

# 或者本地运行
alembic upgrade head
```

### 6. 初始化系统
```bash
# 创建超级管理员和基础数据
python scripts/init_system.py
```

### 7. 验证服务状态
```bash
# 检查所有服务是否运行
docker-compose ps

# 测试健康检查端点
curl http://localhost:8001/health  # Auth服务
curl http://localhost:8002/health  # SSO服务
curl http://localhost:8003/health  # User服务
```

---

## 环境配置

### 创建 .env 文件

如果项目中没有 `.env.example`，创建 `.env` 文件：

```bash
# 数据库配置
DATABASE_URL=postgresql://auth_user:auth_password@localhost:5432/auth_db

# Redis配置
REDIS_URL=redis://localhost:6379/0

# RabbitMQ配置
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# JWT配置
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production
JWT_ALGORITHM=RS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# RSA密钥路径
PRIVATE_KEY_PATH=./private_key.pem
PUBLIC_KEY_PATH=./public_key.pem

# CSRF配置
CSRF_SECRET_KEY=your-csrf-secret-key-change-this-in-production
CSRF_TOKEN_EXPIRE_MINUTES=60

# 邮件配置（可选，用于发送验证邮件）
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=noreply@yourcompany.com
SMTP_FROM_NAME=Your Company

# 短信配置（可选，用于发送验证码）
SMS_PROVIDER=aliyun  # 或 tencent
SMS_ACCESS_KEY_ID=your-access-key-id
SMS_ACCESS_KEY_SECRET=your-access-key-secret
SMS_SIGN_NAME=your-sign-name
SMS_TEMPLATE_CODE=your-template-code

# 应用配置
APP_NAME=统一身份认证平台
APP_VERSION=1.0.0
DEBUG=false
LOG_LEVEL=INFO

# 服务端口
AUTH_SERVICE_PORT=8001
SSO_SERVICE_PORT=8002
USER_SERVICE_PORT=8003
PERMISSION_SERVICE_PORT=8004
SUBSCRIPTION_SERVICE_PORT=8005
NOTIFICATION_SERVICE_PORT=8006
ADMIN_SERVICE_PORT=8007
```

### 安全注意事项

⚠️ **生产环境必须修改以下配置**：
- `JWT_SECRET_KEY` - 使用强随机密钥
- `CSRF_SECRET_KEY` - 使用强随机密钥
- 数据库密码
- Redis密码（如果启用）
- RabbitMQ密码

生成强密钥：
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 数据库初始化

### 方法1：使用Alembic迁移（推荐）

```bash
# 查看当前迁移状态
alembic current

# 查看所有可用迁移
alembic history

# 升级到最新版本
alembic upgrade head

# 如果需要回滚
alembic downgrade -1
```

### 方法2：使用初始化脚本

```bash
# 运行数据库初始化脚本
python scripts/init_db.py
```

### 验证数据库

```bash
# 连接到PostgreSQL
docker-compose exec postgres psql -U auth_user -d auth_db

# 查看所有表
\dt

# 退出
\q
```

---

## 服务启动

### 使用Docker Compose（推荐）

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f auth

# 停止所有服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v
```

### 本地运行（开发环境）

```bash
# 启动基础设施（PostgreSQL, Redis, RabbitMQ）
docker-compose up -d postgres redis rabbitmq

# 安装Python依赖
pip install -r requirements.txt

# 启动认证服务
cd services/auth
uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# 在新终端启动SSO服务
cd services/sso
uvicorn main:app --host 0.0.0.0 --port 8002 --reload

# 在新终端启动其他服务...
```

### 服务端口映射

| 服务 | 端口 | 描述 |
|------|------|------|
| Auth Service | 8001 | 认证服务 |
| SSO Service | 8002 | 单点登录服务 |
| User Service | 8003 | 用户管理服务 |
| Permission Service | 8004 | 权限管理服务 |
| Subscription Service | 8005 | 订阅管理服务 |
| Notification Service | 8006 | 通知服务 |
| Admin Service | 8007 | 管理服务 |
| PostgreSQL | 5432 | 数据库 |
| Redis | 6379 | 缓存 |
| RabbitMQ | 5672 | 消息队列 |
| RabbitMQ Management | 15672 | 管理界面 |

---

## 系统初始化

### 运行初始化脚本

```bash
python scripts/init_system.py
```

这个脚本会：
1. 创建超级管理员账号（用户名：admin，密码：123456）
2. 创建系统角色（super_admin, admin, user）
3. 创建系统权限
4. 创建根组织节点
5. 初始化邮件和短信模板

### 首次登录

超级管理员首次登录后必须修改密码：

```bash
# 1. 登录
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "123456"
  }'

# 响应会提示需要修改密码
# {
#   "detail": "First login, password change required",
#   "password_change_required": true
# }

# 2. 修改密码
curl -X POST http://localhost:8001/api/v1/auth/change-password \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "old_password": "123456",
    "new_password": "NewSecurePassword123!"
  }'
```

---

## API使用示例

### 1. 用户注册（邮箱）

```bash
curl -X POST http://localhost:8001/api/v1/auth/register/email \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "username": "testuser"
  }'
```

### 2. 用户登录

```bash
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "SecurePassword123!"
  }'
```

响应：
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### 3. 获取CSRF Token

```bash
curl -X GET http://localhost:8001/api/v1/auth/csrf-token \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 4. 创建角色（需要管理员权限）

```bash
curl -X POST http://localhost:8004/api/v1/roles \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "X-CSRF-Token: YOUR_CSRF_TOKEN" \
  -d '{
    "name": "developer",
    "description": "开发人员角色"
  }'
```

### 5. 分配角色给用户

```bash
curl -X POST http://localhost:8004/api/v1/users/{user_id}/roles \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "X-CSRF-Token: YOUR_CSRF_TOKEN" \
  -d '{
    "role_id": 2
  }'
```

### 6. SSO授权流程

```bash
# 1. 获取授权码
curl -X GET "http://localhost:8002/api/v1/sso/authorize?client_id=your_client_id&redirect_uri=http://localhost:3000/callback&response_type=code&state=random_state"

# 2. 用授权码换取Token
curl -X POST http://localhost:8002/api/v1/sso/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=AUTH_CODE&client_id=your_client_id&client_secret=your_client_secret&redirect_uri=http://localhost:3000/callback"
```

### 7. 查看审计日志

```bash
curl -X GET "http://localhost:8007/api/v1/admin/audit-logs?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

---

## 测试验证

### 运行所有测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_csrf_protection.py -v

# 运行属性测试
pytest tests/test_csrf_properties.py -v

# 查看测试覆盖率
pytest tests/ --cov=shared --cov=services --cov-report=html
```

### 运行CSRF保护测试

```bash
pytest tests/test_csrf_protection.py tests/test_csrf_properties.py -v
```

预期输出：
```
27 passed, 1 warning in 1.47s
```

### 测试API端点

```bash
# 测试健康检查
curl http://localhost:8001/health

# 测试认证服务
curl http://localhost:8001/docs

# 测试SSO服务
curl http://localhost:8002/docs
```

---

## 常见问题

### 1. 数据库连接失败

**问题**：`could not connect to server: Connection refused`

**解决方案**：
```bash
# 检查PostgreSQL是否运行
docker-compose ps postgres

# 查看PostgreSQL日志
docker-compose logs postgres

# 重启PostgreSQL
docker-compose restart postgres
```

### 2. Redis连接失败

**问题**：`Error connecting to Redis`

**解决方案**：
```bash
# 检查Redis是否运行
docker-compose ps redis

# 测试Redis连接
docker-compose exec redis redis-cli ping
```

### 3. RabbitMQ连接失败

**问题**：`Connection to RabbitMQ failed`

**解决方案**：
```bash
# 检查RabbitMQ是否运行
docker-compose ps rabbitmq

# 访问管理界面
open http://localhost:15672
# 默认用户名/密码: guest/guest
```

### 4. JWT Token验证失败

**问题**：`Invalid token signature`

**解决方案**：
- 确保 `private_key.pem` 和 `public_key.pem` 存在
- 检查环境变量 `PRIVATE_KEY_PATH` 和 `PUBLIC_KEY_PATH`
- 重新生成密钥对：`python scripts/generate_keys.py`

### 5. CSRF Token验证失败

**问题**：`CSRF token missing or invalid`

**解决方案**：
- 确保请求包含 `X-CSRF-Token` 头
- 先调用 `/api/v1/auth/csrf-token` 获取Token
- 检查Token是否过期（默认60分钟）

### 6. 邮件发送失败

**问题**：`SMTP authentication failed`

**解决方案**：
- 检查 `.env` 中的SMTP配置
- 如果使用Gmail，需要启用"应用专用密码"
- 测试SMTP连接：`python scripts/configure_smtp.py`

### 7. 端口被占用

**问题**：`Port 8001 is already in use`

**解决方案**：
```bash
# 查找占用端口的进程
lsof -i :8001

# 杀死进程
kill -9 PID

# 或修改docker-compose.yml中的端口映射
```

### 8. 数据库迁移失败

**问题**：`Target database is not up to date`

**解决方案**：
```bash
# 查看当前版本
alembic current

# 查看迁移历史
alembic history

# 强制升级
alembic upgrade head

# 如果仍然失败，重置数据库
docker-compose down -v
docker-compose up -d postgres
sleep 10
alembic upgrade head
```

---

## 监控和维护

### 查看服务日志

```bash
# 实时查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f auth

# 查看最近100行日志
docker-compose logs --tail=100 auth
```

### 数据库备份

```bash
# 备份数据库
docker-compose exec postgres pg_dump -U auth_user auth_db > backup_$(date +%Y%m%d).sql

# 恢复数据库
docker-compose exec -T postgres psql -U auth_user auth_db < backup_20260129.sql
```

### 清理日志和缓存

```bash
# 清理Docker日志
docker-compose down
docker system prune -a

# 清理Redis缓存
docker-compose exec redis redis-cli FLUSHALL
```

---

## 生产环境部署建议

### 1. 安全配置
- 使用强密码和密钥
- 启用HTTPS（配置SSL证书）
- 配置防火墙规则
- 限制数据库访问
- 定期更新依赖

### 2. 性能优化
- 配置数据库连接池
- 启用Redis持久化
- 配置Nginx反向代理
- 启用CDN加速
- 配置负载均衡

### 3. 监控告警
- 配置Prometheus监控
- 配置Grafana仪表板
- 配置日志收集（ELK）
- 配置告警规则
- 配置健康检查

### 4. 备份策略
- 定期备份数据库
- 备份配置文件
- 备份密钥文件
- 测试恢复流程

---

## 下一步

系统已经完全部署并可以使用。您可以：

1. **开发管理后台**：实现React前端界面
2. **添加更多功能**：实现可选的安全功能
3. **性能优化**：进行压力测试和优化
4. **生产部署**：配置Kubernetes和CI/CD

如有任何问题，请参考：
- 项目文档：`PROJECT_COMPLETION_SUMMARY.md`
- API文档：访问 `http://localhost:8001/docs`
- 测试报告：运行 `pytest tests/ --html=report.html`

---

**祝您使用愉快！** 🎉
