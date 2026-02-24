"""
系统健康检查工具

提供检查各个组件（数据库、Redis、RabbitMQ）健康状态的函数。

需求：13.4 - 提供系统健康检查接口
"""
from typing import Dict, Any
from datetime import datetime
import time


def check_database_health() -> Dict[str, Any]:
    """
    检查数据库连接健康状态
    
    Returns:
        健康状态字典，包含：
        - status: "healthy" 或 "unhealthy"
        - message: 状态消息
        - response_time: 响应时间（毫秒）
        - details: 详细信息
    """
    from shared.database import engine
    from sqlalchemy import text
    
    start_time = time.time()
    
    try:
        # 尝试执行简单查询
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            result.fetchone()
        
        response_time = (time.time() - start_time) * 1000
        
        return {
            "status": "healthy",
            "message": "数据库连接正常",
            "response_time": round(response_time, 2),
            "details": {
                "database_url": engine.url.database,
                "pool_size": engine.pool.size(),
                "checked_at": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        
        return {
            "status": "unhealthy",
            "message": f"数据库连接失败: {str(e)}",
            "response_time": round(response_time, 2),
            "details": {
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat()
            }
        }


def check_redis_health() -> Dict[str, Any]:
    """
    检查Redis连接健康状态
    
    Returns:
        健康状态字典，包含：
        - status: "healthy" 或 "unhealthy"
        - message: 状态消息
        - response_time: 响应时间（毫秒）
        - details: 详细信息
    """
    from shared.redis_client import get_redis
    
    start_time = time.time()
    
    try:
        redis_client = get_redis()
        
        # 尝试执行PING命令
        result = redis_client.ping()
        
        if not result:
            raise Exception("Redis PING返回False")
        
        # 获取Redis信息
        info = redis_client.info()
        
        response_time = (time.time() - start_time) * 1000
        
        return {
            "status": "healthy",
            "message": "Redis连接正常",
            "response_time": round(response_time, 2),
            "details": {
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "checked_at": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        
        return {
            "status": "unhealthy",
            "message": f"Redis连接失败: {str(e)}",
            "response_time": round(response_time, 2),
            "details": {
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat()
            }
        }


def check_rabbitmq_health() -> Dict[str, Any]:
    """
    检查RabbitMQ连接健康状态
    
    Returns:
        健康状态字典，包含：
        - status: "healthy" 或 "unhealthy"
        - message: 状态消息
        - response_time: 响应时间（毫秒）
        - details: 详细信息
    """
    start_time = time.time()
    
    try:
        from shared.rabbitmq_client import get_rabbitmq_connection
        
        # 尝试建立连接
        connection = get_rabbitmq_connection()
        
        # 检查连接是否打开
        if not connection.is_open:
            raise Exception("RabbitMQ连接未打开")
        
        # 获取连接信息
        server_properties = connection._impl.server_properties
        
        # 关闭连接
        connection.close()
        
        response_time = (time.time() - start_time) * 1000
        
        return {
            "status": "healthy",
            "message": "RabbitMQ连接正常",
            "response_time": round(response_time, 2),
            "details": {
                "product": server_properties.get("product", "").decode() if isinstance(server_properties.get("product"), bytes) else server_properties.get("product"),
                "version": server_properties.get("version", "").decode() if isinstance(server_properties.get("version"), bytes) else server_properties.get("version"),
                "checked_at": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        
        return {
            "status": "unhealthy",
            "message": f"RabbitMQ连接失败: {str(e)}",
            "response_time": round(response_time, 2),
            "details": {
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat()
            }
        }


def check_overall_health() -> Dict[str, Any]:
    """
    检查整体系统健康状态
    
    Returns:
        整体健康状态字典，包含：
        - status: "healthy", "degraded" 或 "unhealthy"
        - message: 状态消息
        - timestamp: 检查时间
        - components: 各组件健康状态
    """
    # 检查各个组件
    database_health = check_database_health()
    redis_health = check_redis_health()
    rabbitmq_health = check_rabbitmq_health()
    
    # 统计健康组件数量
    components = {
        "database": database_health,
        "redis": redis_health,
        "rabbitmq": rabbitmq_health
    }
    
    healthy_count = sum(1 for comp in components.values() if comp["status"] == "healthy")
    total_count = len(components)
    
    # 确定整体状态
    if healthy_count == total_count:
        overall_status = "healthy"
        overall_message = "所有组件运行正常"
    elif healthy_count > 0:
        overall_status = "degraded"
        overall_message = f"{healthy_count}/{total_count} 组件运行正常"
    else:
        overall_status = "unhealthy"
        overall_message = "所有组件都不可用"
    
    return {
        "status": overall_status,
        "message": overall_message,
        "timestamp": datetime.utcnow().isoformat(),
        "components": components
    }
