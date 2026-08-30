"""
Pytest配置文件
"""
import pytest
from hypothesis import settings, HealthCheck
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.compiler import compiles


@compiles(UUID, "sqlite")
def compile_postgres_uuid_for_sqlite(_type, _compiler, **_kwargs):
    """The test suite uses SQLite while production models use PostgreSQL UUID."""
    return "CHAR(36)"

# 配置Hypothesis
settings.register_profile(
    "default",
    max_examples=100,  # 每个属性测试至少100次迭代
    deadline=None,  # 禁用超时限制
    suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile("default")
