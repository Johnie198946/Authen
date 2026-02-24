"""
Pytest配置文件
"""
import pytest
from hypothesis import settings, HealthCheck

# 配置Hypothesis
settings.register_profile(
    "default",
    max_examples=100,  # 每个属性测试至少100次迭代
    deadline=None,  # 禁用超时限制
    suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile("default")
