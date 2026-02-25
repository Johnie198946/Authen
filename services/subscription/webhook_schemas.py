"""
Webhook 事件 Pydantic 模型

定义 Webhook 事件的请求/响应数据结构，包含事件类型枚举校验。
"""
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class SubscriptionEventType(str, Enum):
    """订阅事件类型枚举"""
    CREATED = "subscription.created"
    RENEWED = "subscription.renewed"
    UPGRADED = "subscription.upgraded"
    DOWNGRADED = "subscription.downgraded"
    CANCELLED = "subscription.cancelled"
    EXPIRED = "subscription.expired"


class EventData(BaseModel):
    """事件数据"""
    user_id: str = Field(..., description="平台用户 ID")
    plan_id: str = Field(..., description="平台订阅计划 ID")
    effective_date: str = Field(..., description="生效日期 ISO 8601")
    expiry_date: Optional[str] = Field(None, description="到期日期（取消/到期事件可选）")

    @field_validator("user_id", "plan_id")
    @classmethod
    def not_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} 不能为空")
        return v

    @field_validator("effective_date")
    @classmethod
    def validate_effective_date(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("effective_date 不能为空")
        return v


class WebhookEventPayload(BaseModel):
    """Webhook 事件标准化数据结构"""
    event_id: str = Field(..., description="唯一事件标识（幂等键）")
    event_type: SubscriptionEventType = Field(..., description="事件类型枚举")
    timestamp: str = Field(..., description="ISO 8601 格式时间戳")
    data: EventData = Field(..., description="事件数据")

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("event_id 不能为空")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("timestamp 不能为空")
        return v


class WebhookResponse(BaseModel):
    """Webhook 成功响应"""
    event_id: str = Field(..., description="事件 ID")
    status: str = Field(default="processed", description="处理状态")


class WebhookErrorResponse(BaseModel):
    """Webhook 错误响应"""
    error_code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误信息")
    details: Optional[Dict[str, Any]] = Field(default=None, description="详细错误信息")
