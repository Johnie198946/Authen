#!/bin/bash

# 运行SSO会话管理测试

echo "运行SSO会话管理测试..."

# 确保在项目根目录
cd "$(dirname "$0")"

# 设置Python路径
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 运行测试
python3 -m pytest tests/test_sso_session.py -v --tb=short

echo "测试完成"
