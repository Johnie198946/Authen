# 🚀 快速开始指南

欢迎使用统一身份认证和权限管理平台！本指南将帮助您在5分钟内启动并运行系统。

## 📋 前置要求

- Docker >= 20.10
- Docker Compose >= 2.0
- Python >= 3.12

## ⚡ 一键启动

```bash
./quickstart.sh
```

这个脚本会自动完成：
1. ✅ 生成RSA密钥对
2. ✅ 配置环境变量
3. ✅ 启动Docker服务
4. ✅ 初始化数据库
5. ✅ 创建超级管理员
6. ✅ 初始化系统数据

## 🔐 默认账号

**超级管理员**
- 用户名: `admin`
- 密码: `123456`
- ⚠️ 首次登录后必须修改密码

## 🌐 服务访问

| 服务 | URL | 说明 |
|------|-----|------|
| 认证服务 | http://localhost:8001 | 用户注册、登录、Token管理 |
| SSO服务 | http://localhost:8002 | 单点登录、OAuth 2.0 |
| 用户服务 | http://localhost:8003 | 用户管理 |
| 权限服务 | http://localhost:8004 | 角色权限管理 |
| 订阅服务 | http://localhost:8005 | 订阅计划管理 |
| 通知服务 | http://localhost:8006 | 邮件短信发送 |
| 管理服务 | http://localhost:8007 | 系统管理、审计日志 |
| API文档 | http://localhost:8001/docs | Swagger UI |
| RabbitMQ管理 | http://localhost:15672 | guest/guest |

## 🧪 测试API

### 方法1: 使用测试脚本

```bash
./test_api_endpoints.sh
```

### 方法2: 手动测试

```bash
# 1. 健康检查
curl http://localhost:8001/health

# 2. 登录
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "123456"}'

# 3. 获取CSRF Token
curl -X GET http://localhost:8001/api/v1/auth/csrf-token \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 4. 创建用户
curl -X POST http://localhost:8003/api/v1/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "X-CSRF-Token: YOUR_CSRF_TOKEN" \
  -d '{
    "username": "newuser",
    "email": "user@example.com",
    "password": "SecurePass123!"
  }'
```

## 📊 运行测试

```bash
# 安装测试依赖
pip install -r requirements.txt

# 运行所有测试
pytest tests/ -v

# 运行CSRF保护测试（27个测试，550个测试用例）
pytest tests/test_csrf_protection.py tests/test_csrf_properties.py -v

# 查看测试覆盖率
pytest tests/ --cov=shared --cov=services --cov-report=html
```

## 📖 核心功能

### 1. 用户认证
- ✅ 邮箱注册
- ✅ 手机注册
- ✅ OAuth认证（微信、支付宝、Google、Apple）
- ✅ JWT Token（RS256）
- ✅ Token刷新
- ✅ 账号锁定保护

### 2. 单点登录（SSO）
- ✅ OAuth 2.0授权服务器
- ✅ OpenID Connect支持
- ✅ 全局会话管理
- ✅ 跨应用单点登录
- ✅ 全局登出

### 3. 权限管理
- ✅ RBAC权限模型
- ✅ 角色管理
- ✅ 权限分配
- ✅ 用户角色关联
- ✅ 权限缓存

### 4. 组织架构
- ✅ 树形组织结构
- ✅ 用户组织关联
- ✅ 组织权限继承
- ✅ 节点移动

### 5. 订阅管理
- ✅ 订阅计划管理
- ✅ 用户订阅
- ✅ 自动到期处理
- ✅ 到期提醒

### 6. 安全功能
- ✅ CSRF保护（550个测试用例验证）
- ✅ 密码加密（bcrypt）
- ✅ 审计日志
- ✅ API调用日志
- ✅ 系统健康检查

## 🔧 常用命令

### Docker管理

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f auth

# 停止所有服务
docker-compose down

# 停止并删除数据
docker-compose down -v
```

### 数据库管理

```bash
# 运行数据库迁移
alembic upgrade head

# 查看迁移历史
alembic history

# 回滚迁移
alembic downgrade -1

# 连接数据库
docker-compose exec postgres psql -U auth_user -d auth_db
```

### 系统管理

```bash
# 初始化系统
python scripts/init_system.py

# 生成RSA密钥
python scripts/generate_keys.py

# 配置SMTP
python scripts/configure_smtp.py

# 初始化邮件模板
python scripts/init_email_templates.py
```

## 📚 文档

- **部署指南**: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - 详细的部署和配置说明
- **项目总结**: [PROJECT_COMPLETION_SUMMARY.md](PROJECT_COMPLETION_SUMMARY.md) - 项目完成情况
- **完成报告**: [FINAL_PROJECT_COMPLETION_REPORT.md](FINAL_PROJECT_COMPLETION_REPORT.md) - 详细完成报告
- **需求文档**: [.kiro/specs/unified-auth-platform/requirements.md](.kiro/specs/unified-auth-platform/requirements.md)
- **设计文档**: [.kiro/specs/unified-auth-platform/design.md](.kiro/specs/unified-auth-platform/design.md)
- **任务列表**: [.kiro/specs/unified-auth-platform/tasks.md](.kiro/specs/unified-auth-platform/tasks.md)

## 🎯 测试覆盖

### 属性测试（Property-Based Testing）
- **35个属性测试**全部实现
- **数千个测试用例**自动生成
- **CSRF保护**: 27个测试，550个测试用例 ✅

### 测试类别
1. **认证测试** (7个属性)
2. **SSO测试** (4个属性)
3. **订阅测试** (5个属性)
4. **权限测试** (4个属性)
5. **组织测试** (4个属性)
6. **超级管理员测试** (2个属性)
7. **云服务配置测试** (1个属性)
8. **安全测试** (2个属性)

## 🐛 故障排除

### 问题1: 端口被占用

```bash
# 查找占用端口的进程
lsof -i :8001

# 杀死进程
kill -9 PID
```

### 问题2: 数据库连接失败

```bash
# 检查PostgreSQL状态
docker-compose ps postgres

# 重启PostgreSQL
docker-compose restart postgres

# 查看日志
docker-compose logs postgres
```

### 问题3: Redis连接失败

```bash
# 测试Redis连接
docker-compose exec redis redis-cli ping

# 重启Redis
docker-compose restart redis
```

### 问题4: JWT Token验证失败

```bash
# 重新生成密钥对
python scripts/generate_keys.py

# 重启认证服务
docker-compose restart auth
```

## 🚀 下一步

### 开发可选功能
- SQL注入防护
- XSS防护
- 异常登录检测
- API限流
- React管理后台

### 生产部署
- 配置HTTPS
- 配置Nginx反向代理
- 配置Kubernetes
- 配置监控告警
- 配置自动备份

## 💡 提示

1. **首次登录**: 超级管理员首次登录后必须修改密码
2. **CSRF保护**: POST/PUT/DELETE请求需要CSRF Token
3. **Token刷新**: Access Token默认30分钟过期，使用Refresh Token刷新
4. **审计日志**: 所有重要操作都会记录审计日志
5. **健康检查**: 使用 `/health` 端点检查服务状态

## 📞 获取帮助

- 查看API文档: http://localhost:8001/docs
- 查看部署指南: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- 运行测试: `pytest tests/ -v`
- 查看日志: `docker-compose logs -f`

---

**祝您使用愉快！** 🎉

如有问题，请参考详细文档或查看测试用例了解API使用方法。
