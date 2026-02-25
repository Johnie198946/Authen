"""
Webhook HMAC-SHA256 签名验证模块

通过 Application 的 webhook_secret 验证第三方系统推送的 Webhook 请求签名。
"""
import hmac
import hashlib
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from shared.models.application import Application

logger = logging.getLogger(__name__)


async def verify_webhook_signature(
    app_id: str,
    signature: str,
    body: bytes,
    db: Session,
) -> dict:
    """
    验证 Webhook 请求签名。

    1. 通过 app_id 查找 Application
    2. 检查 Application 状态是否为 active
    3. 使用 webhook_secret 计算 HMAC-SHA256
    4. 恒定时间比较签名

    Args:
        app_id: 应用标识
        signature: X-Webhook-Signature 头部值，格式 sha256=<hex>
        body: 原始请求体字节
        db: 数据库会话

    Returns:
        Application 配置字典（id, app_id, name, webhook_secret）

    Raises:
        HTTPException 401: 缺少头部或签名验证失败
        HTTPException 403: 应用不存在或已禁用
    """
    # 1. 校验必要参数
    if not app_id or not signature:
        raise HTTPException(status_code=401, detail="缺少认证头部")

    # 2. 查找 Application
    application = (
        db.query(Application)
        .filter(Application.app_id == app_id)
        .first()
    )

    if not application:
        raise HTTPException(status_code=403, detail="应用不存在或已禁用")

    # 3. 检查状态
    if application.status != "active":
        raise HTTPException(status_code=403, detail="应用不存在或已禁用")

    # 4. 检查 webhook_secret 是否已配置
    if not application.webhook_secret:
        logger.warning("Application %s has no webhook_secret configured", app_id)
        raise HTTPException(status_code=403, detail="应用不存在或已禁用")

    # 5. 解析签名头部格式 sha256=<hex>
    if not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="签名验证失败")

    provided_hex = signature[len("sha256="):]

    # 6. 计算 HMAC-SHA256
    expected_mac = hmac.new(
        application.webhook_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    # 7. 恒定时间比较
    if not hmac.compare_digest(expected_mac, provided_hex):
        logger.warning(
            "Webhook signature verification failed for app_id=%s", app_id
        )
        raise HTTPException(status_code=401, detail="签名验证失败")

    return {
        "id": str(application.id),
        "app_id": application.app_id,
        "name": application.name,
        "webhook_secret": application.webhook_secret,
    }
