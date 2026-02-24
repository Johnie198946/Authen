#!/bin/bash

# API端点测试脚本
# 使用方法: ./test_api_endpoints.sh

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 基础URL
AUTH_URL="http://localhost:8001"
SSO_URL="http://localhost:8002"
USER_URL="http://localhost:8003"
PERMISSION_URL="http://localhost:8004"
ADMIN_URL="http://localhost:8007"

# 变量
ACCESS_TOKEN=""
CSRF_TOKEN=""
USER_ID=""

echo "=========================================="
echo "API端点测试"
echo "=========================================="
echo ""

# 测试函数
test_endpoint() {
    local name=$1
    local method=$2
    local url=$3
    local data=$4
    local headers=$5
    
    echo -e "${BLUE}测试: $name${NC}"
    
    if [ -z "$data" ]; then
        response=$(curl -s -X $method "$url" $headers)
    else
        response=$(curl -s -X $method "$url" -H "Content-Type: application/json" $headers -d "$data")
    fi
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ 成功${NC}"
        echo "响应: $response" | head -c 200
        echo ""
    else
        echo -e "${RED}✗ 失败${NC}"
    fi
    echo ""
}

# 1. 健康检查
echo "=========================================="
echo "1. 健康检查"
echo "=========================================="
echo ""

test_endpoint "认证服务健康检查" "GET" "$AUTH_URL/health"
test_endpoint "SSO服务健康检查" "GET" "$SSO_URL/health"
test_endpoint "用户服务健康检查" "GET" "$USER_URL/health"
test_endpoint "权限服务健康检查" "GET" "$PERMISSION_URL/health"

# 2. 用户登录
echo "=========================================="
echo "2. 用户认证"
echo "=========================================="
echo ""

echo -e "${BLUE}登录超级管理员...${NC}"
login_response=$(curl -s -X POST "$AUTH_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "123456"}')

echo "登录响应: $login_response"
echo ""

# 提取access_token
ACCESS_TOKEN=$(echo $login_response | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ]; then
    echo -e "${RED}✗ 登录失败，无法获取access_token${NC}"
    echo "可能原因："
    echo "1. 系统未初始化，请运行: python scripts/init_system.py"
    echo "2. 超级管理员密码已修改"
    echo "3. 服务未启动"
    exit 1
else
    echo -e "${GREEN}✓ 登录成功${NC}"
    echo "Access Token: ${ACCESS_TOKEN:0:50}..."
fi
echo ""

# 3. 获取CSRF Token
echo "=========================================="
echo "3. 获取CSRF Token"
echo "=========================================="
echo ""

csrf_response=$(curl -s -X GET "$AUTH_URL/api/v1/auth/csrf-token" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "CSRF响应: $csrf_response"
echo ""

CSRF_TOKEN=$(echo $csrf_response | grep -o '"csrf_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$CSRF_TOKEN" ]; then
    echo -e "${YELLOW}⚠ 无法获取CSRF Token，某些操作可能失败${NC}"
else
    echo -e "${GREEN}✓ CSRF Token获取成功${NC}"
    echo "CSRF Token: ${CSRF_TOKEN:0:50}..."
fi
echo ""

# 4. 用户管理
echo "=========================================="
echo "4. 用户管理"
echo "=========================================="
echo ""

# 创建用户
echo -e "${BLUE}创建测试用户...${NC}"
create_user_response=$(curl -s -X POST "$USER_URL/api/v1/users" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "TestPassword123!",
    "is_active": true
  }')

echo "创建用户响应: $create_user_response"
echo ""

USER_ID=$(echo $create_user_response | grep -o '"id":[0-9]*' | head -1 | cut -d':' -f2)

if [ -z "$USER_ID" ]; then
    echo -e "${YELLOW}⚠ 用户可能已存在或创建失败${NC}"
    # 尝试获取用户列表
    users_response=$(curl -s -X GET "$USER_URL/api/v1/users?page=1&page_size=10" \
      -H "Authorization: Bearer $ACCESS_TOKEN")
    echo "用户列表: $users_response"
else
    echo -e "${GREEN}✓ 用户创建成功，ID: $USER_ID${NC}"
fi
echo ""

# 5. 角色和权限
echo "=========================================="
echo "5. 角色和权限管理"
echo "=========================================="
echo ""

# 获取角色列表
echo -e "${BLUE}获取角色列表...${NC}"
roles_response=$(curl -s -X GET "$PERMISSION_URL/api/v1/roles" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "角色列表: $roles_response" | head -c 300
echo ""
echo ""

# 获取权限列表
echo -e "${BLUE}获取权限列表...${NC}"
permissions_response=$(curl -s -X GET "$PERMISSION_URL/api/v1/permissions" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "权限列表: $permissions_response" | head -c 300
echo ""
echo ""

# 6. 审计日志
echo "=========================================="
echo "6. 审计日志"
echo "=========================================="
echo ""

echo -e "${BLUE}获取审计日志...${NC}"
audit_logs_response=$(curl -s -X GET "$ADMIN_URL/api/v1/admin/audit-logs?page=1&page_size=5" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "审计日志: $audit_logs_response" | head -c 500
echo ""
echo ""

# 7. SSO测试
echo "=========================================="
echo "7. SSO功能"
echo "=========================================="
echo ""

echo -e "${BLUE}测试SSO授权端点...${NC}"
echo "注意: SSO授权需要在浏览器中完成完整流程"
echo "授权URL示例:"
echo "$SSO_URL/api/v1/sso/authorize?client_id=test_client&redirect_uri=http://localhost:3000/callback&response_type=code&state=random_state"
echo ""

# 8. 系统信息
echo "=========================================="
echo "8. 系统信息"
echo "=========================================="
echo ""

echo -e "${BLUE}Docker服务状态:${NC}"
docker-compose ps
echo ""

echo -e "${BLUE}数据库连接测试:${NC}"
if docker-compose exec -T postgres pg_isready -U auth_user &> /dev/null; then
    echo -e "${GREEN}✓ PostgreSQL连接正常${NC}"
else
    echo -e "${RED}✗ PostgreSQL连接失败${NC}"
fi

echo -e "${BLUE}Redis连接测试:${NC}"
if docker-compose exec -T redis redis-cli ping &> /dev/null; then
    echo -e "${GREEN}✓ Redis连接正常${NC}"
else
    echo -e "${RED}✗ Redis连接失败${NC}"
fi
echo ""

# 总结
echo "=========================================="
echo "测试总结"
echo "=========================================="
echo ""
echo -e "${GREEN}✓ 基础功能测试完成${NC}"
echo ""
echo "更多测试："
echo "1. 运行单元测试: pytest tests/ -v"
echo "2. 运行属性测试: pytest tests/test_*_properties.py -v"
echo "3. 查看API文档: $AUTH_URL/docs"
echo ""
echo "如需详细测试，请参考 DEPLOYMENT_GUIDE.md"
echo ""
