# 统一身份认证和权限管理平台

企业级IAM（Identity and Access Management）系统，提供集中式的用户认证、授权和订阅管理服务。

## 功能特性

- 🔐 多种认证方式：邮箱、手机、微信、支付宝、Google、Apple
- 🎫 单点登录（SSO）：OAuth 2.0 + OpenID Connect
- 👥 权限管理：基于角色的访问控制（RBAC）
- 🏢 组织架构：树形结构和权限继承
- 💳 订阅管理：统一的订阅系统
- 🎛️ 管理后台：功能完整的Web管理界面
- 🔒 安全防护：CSRF、SQL注入、XSS防护
- 📊 审计日志：完整的操作记录

## 技术栈

**后端：**
- Python 3.11+ / FastAPI
- PostgreSQL 14+
- Redis 7+
- RabbitMQ 3+

**前端：**
- React 18+
- Redux Toolkit
- Ant Design

## 快速开始

### 1. 环境要求

- Python 3.11+
- Docker & Docker Compose
- Node.js 18+ (前端开发)

### 2. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装Python依赖
pip install -r requirements.txt
```

### 3. 启动基础服务

```bash
# 启动PostgreSQL、Redis、RabbitMQ
docker-compose up -d
```

### 4. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑.env文件，配置数据库连接等信息
```

### 5. 数据库迁移

```bash
# 初始化数据库
alembic upgrade head
```

### 6. 启动服务

```bash
# 启动认证服务
cd services/auth
uvicorn main:app --reload --port 8001

# 启动其他服务...
```

## 项目结构

```
.
├── services/              # 微服务目录
│   ├── auth/             # 认证服务
│   ├── sso/              # SSO服务
│   ├── user/             # 用户服务
│   ├── permission/       # 权限服务
│   ├── subscription/     # 订阅服务
│   └── notification/     # 通知服务
├── admin-ui/             # 管理后台前端
├── shared/               # 共享工具库
│   ├── utils/           # 工具函数
│   ├── config.py        # 配置管理
│   ├── database.py      # 数据库连接
│   └── redis_client.py  # Redis客户端
├── alembic/              # 数据库迁移
├── docker-compose.yml    # Docker配置
└── requirements.txt      # Python依赖
```

## API文档

启动服务后访问：
- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc

## 开发指南

详见 `.kiro/specs/unified-auth-platform/` 目录下的规格文档：
- requirements.md - 需求文档
- design.md - 设计文档
- tasks.md - 任务列表

## 许可证

MIT License
