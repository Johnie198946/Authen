"""
Webhook 推送模块

负责向配置了 webhook_url 的应用推送配额预警和耗尽事件。
复用现有 WebhookEventLog 模型记录推送日志。

事件类型:
  - quota.warning: 配额使用率首次超过 80%
  - quota.exhausted: 配额使用率达到 100%

需求: 9.1, 9.2, 9.4
"""
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger("webhook_push")


async def push_quota_webhook(
    app_id: str,
    webhook_url: str,
    webhook_secret: Optional[str],
    event_type: str,
    resource: str,
    current_used: int,
    limit: int,
    reset_timestamp: int,
) -> bool:
    """
    向应用推送配额 Webhook 事件。

    Args:
        app_id: 应用标识
        webhook_url: 应用配置的回调地址
        webhook_secret: 应用的 webhook 签名密钥（可选）
        event_type: 事件类型 (quota.warning / quota.exhausted)
        resource: 资源类型 (request / token)
        current_used: 当前已使用量
        limit: 配额上限
        reset_timestamp: 配额重置时间戳

    Returns:
        True 表示推送成功，False 表示推送失败
    """
    event_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat() + "Z"

    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "data": {
            "app_id": app_id,
            "resource": resource,
            "current_used": current_used,
            "limit": limit,
            "usage_percentage": round((current_used / limit) * 100, 2) if limit > 0 else 0,
            "reset_at": reset_timestamp,
        },
    }

    body = json.dumps(payload, ensure_ascii=False)
    headers = {"Content-Type": "application/json"}

    # 如果配置了 webhook_secret，计算 HMAC-SHA256 签名
    if webhook_secret:
        signature = hmac.new(
            webhook_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    headers["X-Event-Type"] = event_type
    headers["X-Event-Id"] = event_id

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, content=body, headers=headers)
            if response.status_code < 400:
                logger.info(
                    "Webhook pushed | event=%s app_id=%s resource=%s url=%s status=%d",
                    event_type, app_id, resource, webhook_url, response.status_code,
                )
                return True
            else:
                logger.warning(
                    "Webhook push failed | event=%s app_id=%s url=%s status=%d",
                    event_type, app_id, webhook_url, response.status_code,
                )
                return False
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        logger.warning(
            "Webhook push connection failed | event=%s app_id=%s url=%s error=%s",
            event_type, app_id, webhook_url, str(e),
        )
        return False
    except httpx.TimeoutException as e:
        logger.warning(
            "Webhook push timeout | event=%s app_id=%s url=%s error=%s",
            event_type, app_id, webhook_url, str(e),
        )
        return False
    except Exception as e:
        logger.error(
            "Webhook push unexpected error | event=%s app_id=%s url=%s error=%s",
            event_type, app_id, webhook_url, str(e),
        )
        return False
