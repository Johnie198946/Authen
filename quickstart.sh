#!/bin/bash

# 统一身份认证和权限管理平台 - 快速启动脚本
# 使用方法: ./quickstart.sh

set -e

echo "=========================================="
echo "统一身份认证和权限管理平台 - 快速启动"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker未安装${NC}"
    echo "请先安装Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# 检查Docker Compose是否安装
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}错误: Docker Compose未安装${NC}"
    echo "请先安装Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: Python 3未安装${NC}"
    echo "请先安装Python 3.12或更高版本"
    exit 1
fi

echo -e "${GREEN}✓ 环境检查通过${NC}"
echo ""

# 步骤1: 生成RSA密钥对
echo "步骤 1/6: 生成RSA密钥对..."
if [ ! -f "private_key.pem" ] || [ ! -f "public_key.pem" ]; then
    python3 scripts/generate_keys.py
    echo -e "${GREEN}✓ RSA密钥对生成成功${NC}"
else
    echo -e "${YELLOW}⚠ RSA密钥对已存在，跳过生成${NC}"
fi
echo ""

# 步骤2: 配置环境变量
echo "步骤 2/6: 配置环境变量..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${GREEN}✓ 已从.env.example创建.env文件${NC}"
    else
        echo -e "${YELLOW}⚠ .env.example不存在，创建默认.env文件${NC}"
        cat > .env << 'EOF'
# 数据库配置
DATABASE_URL=postgresql://auth_user:auth_password@postgres:5432/auth_db

# Redis配置
REDIS_URL=redis://redis:6379/0

# RabbitMQ配置
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

# JWT配置
JWT_SECRET_KEY=change-this-secret-key-in-production
JWT_ALGORITHM=RS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# RSA密钥路径
PRIVATE_KEY_PATH=./private_key.pem
PUBLIC_KEY_PATH=./public_key.pem

# CSRF配置
CSRF_SECRET_KEY=change-this-csrf-secret-in-production
CSRF_TOKEN_EXPIRE_MINUTES=60

# 应用配置
APP_NAME=统一身份认证平台
DEBUG=false
LOG_LEVEL=INFO
EOF
        echo -e "${GREEN}✓ 默认.env文件创建成功${NC}"
    fi
    echo -e "${YELLOW}⚠ 请编辑.env文件，配置必要的环境变量${NC}"
else
    echo -e "${YELLOW}⚠ .env文件已存在，跳过创建${NC}"
fi
echo ""

# 步骤3: 启动Docker服务
echo "步骤 3/6: 启动Docker服务..."
docker-compose up -d
echo -e "${GREEN}✓ Docker服务启动成功${NC}"
echo ""

# 步骤4: 等待服务就绪
echo "步骤 4/6: 等待服务就绪..."
echo "等待PostgreSQL启动..."
sleep 10

# 检查PostgreSQL是否就绪
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if docker-compose exec -T postgres pg_isready -U auth_user &> /dev/null; then
        echo -e "${GREEN}✓ PostgreSQL已就绪${NC}"
        break
    fi
    attempt=$((attempt + 1))
    echo "等待PostgreSQL... ($attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo -e "${RED}错误: PostgreSQL启动超时${NC}"
    exit 1
fi

# 检查Redis是否就绪
if docker-compose exec -T redis redis-cli ping &> /dev/null; then
    echo -e "${GREEN}✓ Redis已就绪${NC}"
else
    echo -e "${YELLOW}⚠ Redis未就绪，但继续执行${NC}"
fi
echo ""

# 步骤5: 初始化数据库
echo "步骤 5/6: 初始化数据库..."
if command -v alembic &> /dev/null; then
    alembic upgrade head
    echo -e "${GREEN}✓ 数据库迁移完成${NC}"
else
    echo -e "${YELLOW}⚠ Alembic未安装，跳过数据库迁移${NC}"
    echo "请手动运行: pip install alembic && alembic upgrade head"
fi
echo ""

# 步骤6: 初始化系统
echo "步骤 6/6: 初始化系统..."
if [ -f "scripts/init_system.py" ]; then
    python3 scripts/init_system.py
    echo -e "${GREEN}✓ 系统初始化完成${NC}"
else
    echo -e "${YELLOW}⚠ init_system.py不存在，跳过系统初始化${NC}"
fi
echo ""

# 显示服务状态
echo "=========================================="
echo "服务状态"
echo "=========================================="
docker-compose ps
echo ""

# 显示访问信息
echo "=========================================="
echo "访问信息"
echo "=========================================="
echo ""
echo -e "${GREEN}认证服务:${NC}      http://localhost:8001"
echo -e "${GREEN}SSO服务:${NC}       http://localhost:8002"
echo -e "${GREEN}用户服务:${NC}      http://localhost:8003"
echo -e "${GREEN}权限服务:${NC}      http://localhost:8004"
echo -e "${GREEN}订阅服务:${NC}      http://localhost:8005"
echo -e "${GREEN}通知服务:${NC}      http://localhost:8006"
echo -e "${GREEN}管理服务:${NC}      http://localhost:8007"
echo ""
echo -e "${GREEN}API文档:${NC}       http://localhost:8001/docs"
echo -e "${GREEN}RabbitMQ管理:${NC}  http://localhost:15672 (guest/guest)"
echo ""
echo "=========================================="
echo "默认超级管理员账号"
echo "=========================================="
echo ""
echo -e "${YELLOW}用户名:${NC} admin"
echo -e "${YELLOW}密码:${NC}   123456"
echo -e "${RED}⚠ 首次登录后必须修改密码${NC}"
echo ""
echo "=========================================="
echo "测试API"
echo "=========================================="
echo ""
echo "# 健康检查"
echo "curl http://localhost:8001/health"
echo ""
echo "# 登录"
echo 'curl -X POST http://localhost:8001/api/v1/auth/login \'
echo '  -H "Content-Type: application/json" \'
echo '  -d '"'"'{"username": "admin", "password": "123456"}'"'"
echo ""
echo "=========================================="
echo "查看日志"
echo "=========================================="
echo ""
echo "# 查看所有服务日志"
echo "docker-compose logs -f"
echo ""
echo "# 查看特定服务日志"
echo "docker-compose logs -f auth"
echo ""
echo "=========================================="
echo "停止服务"
echo "=========================================="
echo ""
echo "docker-compose down"
echo ""
echo -e "${GREEN}✓ 快速启动完成！${NC}"
echo ""
