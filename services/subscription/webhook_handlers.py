"""
Webhook 事件处理器

实现六种订阅事件类型的处理函数，每个处理函数：
1. 校验 user_id 是否属于该 Application 的 AppUser 绑定
2. 校验 plan_id 对应的订阅计划是否存在且活跃
3. 执行对应的订阅变更操作
4. 返回处理结果摘要
"""
import uuid as uuid_lib
import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from shared.models.application import Application, AppUser
from shared.models.subscription import SubscriptionPlan, UserSubscription

logger = logging.getLogger(__name__)


def _parse_uuid(value: str, field_name: str) -> uuid_lib.UUID:
    """Parse a string to UUID, raise HTTPException 422 on failure."""
    try:
        return uuid_lib.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"无效的 {field_name} 格式")


def _validate_app_user(app_id: str, user_id_str: str, db: Session) -> uuid_lib.UUID:
    """
    Validate that user_id belongs to the Application via AppUser binding.

    Returns the parsed user UUID.
    Raises HTTPException 422 if the binding does not exist.
    """
    user_uuid = _parse_uuid(user_id_str, "user_id")

    application = (
        db.query(Application)
        .filter(Application.app_id == app_id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=422, detail="用户不属于该应用")

    binding = (
        db.query(AppUser)
        .filter(
            AppUser.application_id == application.id,
            AppUser.user_id == user_uuid,
        )
        .first()
    )
    if not binding:
        raise HTTPException(status_code=422, detail="用户不属于该应用")

    return user_uuid


def _validate_plan(plan_id_str: str, db: Session) -> uuid_lib.UUID:
    """
    Validate that plan_id corresponds to an existing active SubscriptionPlan.

    Returns the parsed plan UUID.
    Raises HTTPException 422 if the plan does not exist or is inactive.
    """
    plan_uuid = _parse_uuid(plan_id_str, "plan_id")

    plan = (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.id == plan_uuid)
        .first()
    )
    if not plan or not plan.is_active:
        raise HTTPException(status_code=422, detail="订阅计划无效")

    return plan_uuid


def _parse_datetime(date_str: str, field_name: str) -> datetime:
    """Parse an ISO 8601 date string to datetime."""
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=422, detail=f"无效的 {field_name} 日期格式"
        )


async def handle_subscription_created(
    app_id: str, data: dict, db: Session
) -> dict:
    """
    处理 subscription.created 事件。

    校验 AppUser 绑定和 plan_id 有效性，创建活跃订阅记录。
    """
    user_uuid = _validate_app_user(app_id, data["user_id"], db)
    plan_uuid = _validate_plan(data["plan_id"], db)

    effective_date = _parse_datetime(data["effective_date"], "effective_date")
    expiry_date = (
        _parse_datetime(data["expiry_date"], "expiry_date")
        if data.get("expiry_date")
        else None
    )

    # Determine end_date: use expiry_date if provided, otherwise calculate from plan
    if expiry_date:
        end_date = expiry_date
    else:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_uuid).first()
        from datetime import timedelta
        end_date = effective_date + timedelta(days=plan.duration_days)

    subscription = UserSubscription(
        user_id=user_uuid,
        plan_id=plan_uuid,
        status="active",
        start_date=effective_date,
        end_date=end_date,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)

    return {
        "action": "created",
        "subscription_id": str(subscription.id),
        "user_id": str(user_uuid),
        "plan_id": str(plan_uuid),
        "status": "active",
    }


async def handle_subscription_renewed(
    app_id: str, data: dict, db: Session
) -> dict:
    """
    处理 subscription.renewed 事件。

    更新订阅到期日期。
    """
    user_uuid = _validate_app_user(app_id, data["user_id"], db)
    _validate_plan(data["plan_id"], db)

    expiry_date = _parse_datetime(
        data.get("expiry_date") or data["effective_date"], "expiry_date"
    )

    subscription = (
        db.query(UserSubscription)
        .filter(
            UserSubscription.user_id == user_uuid,
            UserSubscription.status == "active",
        )
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=422, detail="未找到活跃订阅")

    subscription.end_date = expiry_date
    subscription.updated_at = datetime.utcnow()
    db.commit()

    return {
        "action": "renewed",
        "subscription_id": str(subscription.id),
        "user_id": str(user_uuid),
        "new_end_date": expiry_date.isoformat(),
    }


async def handle_subscription_upgraded(
    app_id: str, data: dict, db: Session
) -> dict:
    """
    处理 subscription.upgraded 事件。

    更新订阅计划为目标计划。
    """
    user_uuid = _validate_app_user(app_id, data["user_id"], db)
    plan_uuid = _validate_plan(data["plan_id"], db)

    subscription = (
        db.query(UserSubscription)
        .filter(
            UserSubscription.user_id == user_uuid,
            UserSubscription.status == "active",
        )
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=422, detail="未找到活跃订阅")

    old_plan_id = str(subscription.plan_id)
    subscription.plan_id = plan_uuid
    subscription.updated_at = datetime.utcnow()

    # Update expiry_date if provided
    if data.get("expiry_date"):
        subscription.end_date = _parse_datetime(data["expiry_date"], "expiry_date")

    db.commit()

    return {
        "action": "upgraded",
        "subscription_id": str(subscription.id),
        "user_id": str(user_uuid),
        "old_plan_id": old_plan_id,
        "new_plan_id": str(plan_uuid),
    }


async def handle_subscription_downgraded(
    app_id: str, data: dict, db: Session
) -> dict:
    """
    处理 subscription.downgraded 事件。

    更新订阅计划为目标计划。
    """
    user_uuid = _validate_app_user(app_id, data["user_id"], db)
    plan_uuid = _validate_plan(data["plan_id"], db)

    subscription = (
        db.query(UserSubscription)
        .filter(
            UserSubscription.user_id == user_uuid,
            UserSubscription.status == "active",
        )
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=422, detail="未找到活跃订阅")

    old_plan_id = str(subscription.plan_id)
    subscription.plan_id = plan_uuid
    subscription.updated_at = datetime.utcnow()

    # Update expiry_date if provided
    if data.get("expiry_date"):
        subscription.end_date = _parse_datetime(data["expiry_date"], "expiry_date")

    db.commit()

    return {
        "action": "downgraded",
        "subscription_id": str(subscription.id),
        "user_id": str(user_uuid),
        "old_plan_id": old_plan_id,
        "new_plan_id": str(plan_uuid),
    }


async def handle_subscription_cancelled(
    app_id: str, data: dict, db: Session
) -> dict:
    """
    处理 subscription.cancelled 事件。

    设置订阅状态为 cancelled。
    """
    user_uuid = _validate_app_user(app_id, data["user_id"], db)
    _validate_plan(data["plan_id"], db)

    subscription = (
        db.query(UserSubscription)
        .filter(
            UserSubscription.user_id == user_uuid,
            UserSubscription.status == "active",
        )
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=422, detail="未找到活跃订阅")

    subscription.status = "cancelled"
    subscription.updated_at = datetime.utcnow()
    db.commit()

    return {
        "action": "cancelled",
        "subscription_id": str(subscription.id),
        "user_id": str(user_uuid),
        "status": "cancelled",
    }


async def handle_subscription_expired(
    app_id: str, data: dict, db: Session
) -> dict:
    """
    处理 subscription.expired 事件。

    设置订阅状态为 expired。
    """
    user_uuid = _validate_app_user(app_id, data["user_id"], db)
    _validate_plan(data["plan_id"], db)

    subscription = (
        db.query(UserSubscription)
        .filter(
            UserSubscription.user_id == user_uuid,
            UserSubscription.status == "active",
        )
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=422, detail="未找到活跃订阅")

    subscription.status = "expired"
    subscription.updated_at = datetime.utcnow()
    db.commit()

    return {
        "action": "expired",
        "subscription_id": str(subscription.id),
        "user_id": str(user_uuid),
        "status": "expired",
    }
