"""
配置管理模块
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """应用配置"""
    
    # 数据库配置
    DATABASE_URL: str = "postgresql://authuser:authpass123@localhost:5433/auth"
    
    # Redis配置
    REDIS_URL: str = "redis://localhost:6380/0"
    
    # RabbitMQ配置
    RABBITMQ_URL: str = "amqp://authuser:authpass123@localhost:5672"
    
    # JWT配置
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"  # 使用HS256而不是RS256以简化开发
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    
    # SSO会话配置
    SSO_SESSION_EXPIRE_HOURS: int = 24  # SSO会话过期时间（小时）
    
    # 应用配置
    APP_NAME: str = "Unified Auth Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # CORS配置
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:5174"]
    
    # OAuth配置
    # 微信OAuth
    WECHAT_APP_ID: str = "your_wechat_app_id"
    WECHAT_APP_SECRET: str = "your_wechat_app_secret"
    
    # 支付宝OAuth
    ALIPAY_APP_ID: str = "your_alipay_app_id"
    ALIPAY_APP_SECRET: str = "your_alipay_app_secret"
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str = "your_google_client_id"
    GOOGLE_CLIENT_SECRET: str = "your_google_client_secret"
    
    # Apple OAuth
    APPLE_CLIENT_ID: str = "your_apple_client_id"
    APPLE_CLIENT_SECRET: str = "your_apple_client_secret"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
