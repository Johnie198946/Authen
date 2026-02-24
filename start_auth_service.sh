#!/bin/bash

# 启动认证服务脚本

echo "🚀 启动统一身份认证平台 - 认证服务"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误：未找到Python3"
    exit 1
fi

# 检查Docker服务
echo "📦 检查Docker服务..."
if ! docker ps &> /dev/null; then
    echo "❌ 错误：Docker未运行或无权限访问"
    echo "请先启动Docker Desktop"
    exit 1
fi

# 检查数据库容器
if ! docker ps | grep -q auth_postgres; then
    echo "⚠️  数据库容器未运行，正在启动..."
    docker-compose up -d postgres redis rabbitmq
    echo "等待数据库启动..."
    sleep 5
fi

# 初始化数据库
echo "🗄️  初始化数据库..."
python3 scripts/init_db.py

# 启动认证服务
echo ""
echo "✅ 启动认证服务..."
echo "📖 API文档: http://localhost:8001/docs"
echo ""
cd services/auth && python3 main.py
