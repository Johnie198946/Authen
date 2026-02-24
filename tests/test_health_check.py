"""
系统健康检查测试

测试健康检查功能，验证：
- 数据库连接检查
- Redis连接检查
- RabbitMQ连接检查
- 整体健康状态

需求：13.4 - 提供系统健康检查接口
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.database import Base
from shared.utils.health_check import (
    check_database_health,
    check_redis_health,
    check_rabbitmq_health,
    check_overall_health
)


# 测试数据库设置
TEST_DATABASE_URL = "sqlite:///./test_health_check.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """创建测试数据库"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_check_database_health_success():
    """
    测试数据库健康检查 - 成功情况
    
    验证：
    - 返回healthy状态
    - 包含响应时间
    - 包含数据库详情
    """
    result = check_database_health()
    
    assert result["status"] == "healthy"
    assert result["message"] == "数据库连接正常"
    assert "response_time" in result
    assert result["response_time"] > 0
    assert "details" in result
    assert "database_url" in result["details"]
    assert "checked_at" in result["details"]


def test_check_database_health_failure():
    """
    测试数据库健康检查 - 失败情况
    
    验证：
    - 返回unhealthy状态
    - 包含错误信息
    """
    with patch('shared.database.engine') as mock_engine:
        # 模拟数据库连接失败
        mock_engine.connect.side_effect = Exception("Connection failed")
        
        result = check_database_health()
        
        assert result["status"] == "unhealthy"
        assert "数据库连接失败" in result["message"]
        assert "response_time" in result
        assert "error" in result["details"]


def test_check_redis_health_success():
    """
    测试Redis健康检查 - 成功情况
    
    验证：
    - 返回healthy状态
    - 包含响应时间
    - 包含Redis详情
    """
    with patch('shared.redis_client.get_redis') as mock_get_redis:
        # 模拟Redis客户端
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {
            "redis_version": "7.0.0",
            "connected_clients": 5,
            "used_memory_human": "1.5M"
        }
        mock_get_redis.return_value = mock_redis
        
        result = check_redis_health()
        
        assert result["status"] == "healthy"
        assert result["message"] == "Redis连接正常"
        assert "response_time" in result
        assert result["response_time"] > 0
        assert "details" in result
        assert result["details"]["redis_version"] == "7.0.0"
        assert result["details"]["connected_clients"] == 5


def test_check_redis_health_failure():
    """
    测试Redis健康检查 - 失败情况
    
    验证：
    - 返回unhealthy状态
    - 包含错误信息
    """
    with patch('shared.redis_client.get_redis') as mock_get_redis:
        # 模拟Redis连接失败
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Connection refused")
        mock_get_redis.return_value = mock_redis
        
        result = check_redis_health()
        
        assert result["status"] == "unhealthy"
        assert "Redis连接失败" in result["message"]
        assert "response_time" in result
        assert "error" in result["details"]


def test_check_rabbitmq_health_success():
    """
    测试RabbitMQ健康检查 - 成功情况
    
    验证：
    - 返回healthy状态
    - 包含响应时间
    - 包含RabbitMQ详情
    """
    with patch('shared.rabbitmq_client.get_rabbitmq_connection') as mock_get_connection:
        # 模拟RabbitMQ连接
        mock_connection = MagicMock()
        mock_connection.is_open = True
        mock_connection._impl.server_properties = {
            "product": b"RabbitMQ",
            "version": b"3.11.0"
        }
        mock_get_connection.return_value = mock_connection
        
        result = check_rabbitmq_health()
        
        assert result["status"] == "healthy"
        assert result["message"] == "RabbitMQ连接正常"
        assert "response_time" in result
        assert result["response_time"] > 0
        assert "details" in result
        assert result["details"]["product"] == "RabbitMQ"
        assert result["details"]["version"] == "3.11.0"


def test_check_rabbitmq_health_failure():
    """
    测试RabbitMQ健康检查 - 失败情况
    
    验证：
    - 返回unhealthy状态
    - 包含错误信息
    """
    with patch('shared.rabbitmq_client.get_rabbitmq_connection') as mock_get_connection:
        # 模拟RabbitMQ连接失败
        mock_get_connection.side_effect = Exception("Connection refused")
        
        result = check_rabbitmq_health()
        
        assert result["status"] == "unhealthy"
        assert "RabbitMQ连接失败" in result["message"]
        assert "response_time" in result
        assert "error" in result["details"]


def test_check_overall_health_all_healthy():
    """
    测试整体健康检查 - 所有组件健康
    
    验证：
    - 返回healthy状态
    - 包含所有组件状态
    - 消息正确
    """
    with patch('shared.utils.health_check.check_database_health') as mock_db, \
         patch('shared.utils.health_check.check_redis_health') as mock_redis, \
         patch('shared.utils.health_check.check_rabbitmq_health') as mock_rabbitmq:
        
        # 模拟所有组件健康
        mock_db.return_value = {"status": "healthy", "message": "OK"}
        mock_redis.return_value = {"status": "healthy", "message": "OK"}
        mock_rabbitmq.return_value = {"status": "healthy", "message": "OK"}
        
        result = check_overall_health()
        
        assert result["status"] == "healthy"
        assert result["message"] == "所有组件运行正常"
        assert "timestamp" in result
        assert "components" in result
        assert len(result["components"]) == 3
        assert result["components"]["database"]["status"] == "healthy"
        assert result["components"]["redis"]["status"] == "healthy"
        assert result["components"]["rabbitmq"]["status"] == "healthy"


def test_check_overall_health_degraded():
    """
    测试整体健康检查 - 部分组件不健康
    
    验证：
    - 返回degraded状态
    - 包含所有组件状态
    - 消息显示健康组件数量
    """
    with patch('shared.utils.health_check.check_database_health') as mock_db, \
         patch('shared.utils.health_check.check_redis_health') as mock_redis, \
         patch('shared.utils.health_check.check_rabbitmq_health') as mock_rabbitmq:
        
        # 模拟部分组件不健康
        mock_db.return_value = {"status": "healthy", "message": "OK"}
        mock_redis.return_value = {"status": "unhealthy", "message": "Failed"}
        mock_rabbitmq.return_value = {"status": "healthy", "message": "OK"}
        
        result = check_overall_health()
        
        assert result["status"] == "degraded"
        assert "2/3" in result["message"]
        assert "components" in result
        assert result["components"]["database"]["status"] == "healthy"
        assert result["components"]["redis"]["status"] == "unhealthy"
        assert result["components"]["rabbitmq"]["status"] == "healthy"


def test_check_overall_health_all_unhealthy():
    """
    测试整体健康检查 - 所有组件不健康
    
    验证：
    - 返回unhealthy状态
    - 包含所有组件状态
    - 消息正确
    """
    with patch('shared.utils.health_check.check_database_health') as mock_db, \
         patch('shared.utils.health_check.check_redis_health') as mock_redis, \
         patch('shared.utils.health_check.check_rabbitmq_health') as mock_rabbitmq:
        
        # 模拟所有组件不健康
        mock_db.return_value = {"status": "unhealthy", "message": "Failed"}
        mock_redis.return_value = {"status": "unhealthy", "message": "Failed"}
        mock_rabbitmq.return_value = {"status": "unhealthy", "message": "Failed"}
        
        result = check_overall_health()
        
        assert result["status"] == "unhealthy"
        assert result["message"] == "所有组件都不可用"
        assert "components" in result
        assert result["components"]["database"]["status"] == "unhealthy"
        assert result["components"]["redis"]["status"] == "unhealthy"
        assert result["components"]["rabbitmq"]["status"] == "unhealthy"


def test_health_check_response_time():
    """
    测试健康检查响应时间
    
    验证：
    - 响应时间被正确记录
    - 响应时间为正数
    """
    result = check_database_health()
    
    assert "response_time" in result
    assert isinstance(result["response_time"], (int, float))
    assert result["response_time"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
