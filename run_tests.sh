#!/bin/bash
# 测试运行脚本

echo "运行JWT Token测试..."
python3 -m pytest tests/test_jwt_tokens.py -v --tb=short

echo ""
echo "运行密码加密测试..."
python3 -m pytest tests/test_crypto.py -v --tb=short

echo ""
echo "运行所有测试..."
python3 -m pytest tests/ -v --tb=short
