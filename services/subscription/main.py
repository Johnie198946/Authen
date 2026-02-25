"""
订阅服务
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timedelta
import json
import traceback
from shared.database import get_db
from shared.models.subscription import SubscriptionPlan, UserSubscription
from shared.models.application import Application, AppSubscriptionPlan
from shared.models.quota import AppQuotaOverride, QuotaUsage
from shared.models.webhook import WebhookEventLog
from shared.config import settings
from shared.redis_client import get_redis
from shared.utils.audit_log import create_audit_log
from services.subscription.webhook_auth import verify_webhook_signature
from services.subscription.webhook_schemas import WebhookEventPayload, WebhookResponse, WebhookErrorResponse
from services.subscription.webhook_handlers import (
    handle_subscription_created,
    handle_subscription_renewed,
    handle_subscription_upgraded,
    handle_subscription_downgraded,
    handle_subscription_cancelled,
    handle_subscription_expired,
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="订阅服务", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class PlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    duration_days: int
    price: float
    features: Optional[dict] = None
    request_quota: Optional[int] = -1
    token_quota: Optional[int] = -1
    quota_period_days: Optional[int] = 30

class PlanResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    duration_days: int
    price: float
    is_active: bool
    request_quota: int
    token_quota: int
    quota_period_days: int

class SubscriptionCreate(BaseModel):
    plan_id: str
    auto_renew: bool = True

class SubscriptionResponse(BaseModel):
    id: str
    user_id: str
    plan_id: str
    status: str
    start_date: datetime
    end_date: datetime
    auto_renew: bool

@app.get("/")
async def root():
    return {"service": "订阅服务", "status": "running"}

@app.get("/api/v1/subscriptions/plans", response_model=List[PlanResponse])
async def list_plans(db: Session = Depends(get_db)):
    """获取订阅计划列表"""
    plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).all()
    return [PlanResponse(id=str(p.id), name=p.name, description=p.description, duration_days=p.duration_days, price=float(p.price), is_active=p.is_active, request_quota=p.request_quota, token_quota=p.token_quota, quota_period_days=p.quota_period_days) for p in plans]

@app.post("/api/v1/subscriptions/plans", response_model=PlanResponse)
async def create_plan(plan_data: PlanCreate, db: Session = Depends(get_db)):
    """创建订阅计划"""
    # 验证配额值
    if plan_data.request_quota is not None and plan_data.request_quota < -1:
        raise HTTPException(status_code=400, detail={"error_code": "invalid_quota_value", "message": "request_quota 必须 >= -1"})
    if plan_data.token_quota is not None and plan_data.token_quota < -1:
        raise HTTPException(status_code=400, detail={"error_code": "invalid_quota_value", "message": "token_quota 必须 >= -1"})
    if plan_data.quota_period_days is not None and plan_data.quota_period_days < 1:
        raise HTTPException(status_code=400, detail={"error_code": "invalid_quota_value", "message": "quota_period_days 必须 >= 1"})
    plan = SubscriptionPlan(
        name=plan_data.name,
        description=plan_data.description,
        duration_days=plan_data.duration_days,
        price=plan_data.price,
        features=plan_data.features,
        request_quota=plan_data.request_quota if plan_data.request_quota is not None else -1,
        token_quota=plan_data.token_quota if plan_data.token_quota is not None else -1,
        quota_period_days=plan_data.quota_period_days if plan_data.quota_period_days is not None else 30,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return PlanResponse(id=str(plan.id), name=plan.name, description=plan.description, duration_days=plan.duration_days, price=float(plan.price), is_active=plan.is_active, request_quota=plan.request_quota, token_quota=plan.token_quota, quota_period_days=plan.quota_period_days)

@app.put("/api/v1/subscriptions/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(plan_id: str, plan_data: PlanCreate, db: Session = Depends(get_db)):
    """更新订阅计划"""
    import uuid as uuid_lib
    try:
        plan_uuid = uuid_lib.UUID(plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的计划ID")
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_uuid).first()
    if not plan:
        raise HTTPException(status_code=404, detail="订阅计划不存在")
    # 验证配额值
    if plan_data.request_quota is not None and plan_data.request_quota < -1:
        raise HTTPException(status_code=400, detail={"error_code": "invalid_quota_value", "message": "request_quota 必须 >= -1"})
    if plan_data.token_quota is not None and plan_data.token_quota < -1:
        raise HTTPException(status_code=400, detail={"error_code": "invalid_quota_value", "message": "token_quota 必须 >= -1"})
    if plan_data.quota_period_days is not None and plan_data.quota_period_days < 1:
        raise HTTPException(status_code=400, detail={"error_code": "invalid_quota_value", "message": "quota_period_days 必须 >= 1"})
    plan.name = plan_data.name
    plan.description = plan_data.description
    plan.duration_days = plan_data.duration_days
    plan.price = plan_data.price
    if plan_data.features is not None:
        plan.features = plan_data.features
    if plan_data.request_quota is not None:
        plan.request_quota = plan_data.request_quota
    if plan_data.token_quota is not None:
        plan.token_quota = plan_data.token_quota
    if plan_data.quota_period_days is not None:
        plan.quota_period_days = plan_data.quota_period_days
    db.commit()
    db.refresh(plan)
    return PlanResponse(id=str(plan.id), name=plan.name, description=plan.description, duration_days=plan.duration_days, price=float(plan.price), is_active=plan.is_active, request_quota=plan.request_quota, token_quota=plan.token_quota, quota_period_days=plan.quota_period_days)

@app.delete("/api/v1/subscriptions/plans/{plan_id}")
async def delete_plan(plan_id: str, db: Session = Depends(get_db)):
    """删除订阅计划（软删除，设为不活跃）"""
    import uuid as uuid_lib
    try:
        plan_uuid = uuid_lib.UUID(plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的计划ID")
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_uuid).first()
    if not plan:
        raise HTTPException(status_code=404, detail="订阅计划不存在")
    # 检查是否有活跃订阅在使用
    active_subs = db.query(UserSubscription).filter(UserSubscription.plan_id == plan_uuid, UserSubscription.status == 'active').count()
    if active_subs > 0:
        raise HTTPException(status_code=400, detail=f"该计划有 {active_subs} 个活跃订阅，无法删除")
    plan.is_active = False
    db.commit()
    return {"success": True, "message": "订阅计划已停用"}

@app.get("/api/v1/users/{user_id}/subscription")
async def get_user_subscription(user_id: str, db: Session = Depends(get_db)):
    """获取用户订阅"""
    import uuid as uuid_lib
    try:
        user_uuid = uuid_lib.UUID(user_id) if isinstance(user_id, str) else user_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的用户ID格式")
    
    sub = db.query(UserSubscription).filter(UserSubscription.user_id == user_uuid, UserSubscription.status == 'active').first()
    if not sub:
        return {"subscription": None}
    return SubscriptionResponse(id=str(sub.id), user_id=str(sub.user_id), plan_id=str(sub.plan_id), status=sub.status, start_date=sub.start_date, end_date=sub.end_date, auto_renew=sub.auto_renew)

@app.post("/api/v1/users/{user_id}/subscription", response_model=SubscriptionResponse)
async def create_subscription(user_id: str, sub_data: SubscriptionCreate, db: Session = Depends(get_db)):
    """创建用户订阅"""
    import uuid as uuid_lib
    # Convert string IDs to UUID objects for database queries
    try:
        plan_uuid = uuid_lib.UUID(sub_data.plan_id) if isinstance(sub_data.plan_id, str) else sub_data.plan_id
        user_uuid = uuid_lib.UUID(user_id) if isinstance(user_id, str) else user_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的ID格式")
    
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_uuid).first()
    if not plan:
        raise HTTPException(status_code=404, detail="订阅计划不存在")
    
    existing = db.query(UserSubscription).filter(UserSubscription.user_id == user_uuid, UserSubscription.status == 'active').first()
    if existing:
        raise HTTPException(status_code=409, detail="用户已有活跃订阅")
    
    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=plan.duration_days)
    
    subscription = UserSubscription(user_id=user_uuid, plan_id=plan_uuid, status='active', start_date=start_date, end_date=end_date, auto_renew=sub_data.auto_renew)
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return SubscriptionResponse(id=str(subscription.id), user_id=str(subscription.user_id), plan_id=str(subscription.plan_id), status=subscription.status, start_date=subscription.start_date, end_date=subscription.end_date, auto_renew=subscription.auto_renew)

@app.delete("/api/v1/users/{user_id}/subscription")
async def cancel_subscription(user_id: str, db: Session = Depends(get_db)):
    """取消用户订阅"""
    import uuid as uuid_lib
    try:
        user_uuid = uuid_lib.UUID(user_id) if isinstance(user_id, str) else user_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的用户ID格式")
    
    sub = db.query(UserSubscription).filter(UserSubscription.user_id == user_uuid, UserSubscription.status == 'active').first()
    if not sub:
        raise HTTPException(status_code=404, detail="未找到活跃订阅")
    sub.auto_renew = False
    db.commit()
    return {"success": True, "message": "订阅将在当前周期结束后停止"}


def process_expired_subscriptions(db: Session) -> dict:
    """
    处理到期订阅
    
    检查所有到期的订阅，将状态更新为expired，并降级用户权限。
    这个函数应该由定时任务每小时调用一次。
    
    返回：处理结果统计
    """
    now = datetime.utcnow()
    
    # 查找所有到期的活跃订阅
    expired_subs = db.query(UserSubscription).filter(
        UserSubscription.status == 'active',
        UserSubscription.end_date <= now
    ).all()
    
    processed_count = 0
    for sub in expired_subs:
        # 更新订阅状态为expired
        sub.status = 'expired'
        sub.updated_at = now
        processed_count += 1
        
        logger.info(f"Expired subscription {sub.id} for user {sub.user_id}")
    
    db.commit()
    
    return {
        "processed": processed_count,
        "timestamp": now.isoformat()
    }


def send_expiration_reminders(db: Session) -> dict:
    """
    发送订阅到期提醒
    
    检查所有将在7天内到期的订阅，发送提醒通知给用户。
    这个函数应该由定时任务每天调用一次。
    
    返回：发送提醒的统计
    """
    now = datetime.utcnow()
    reminder_threshold = now + timedelta(days=7)
    
    # 查找所有将在7天内到期的活跃订阅
    expiring_soon_subs = db.query(UserSubscription).filter(
        UserSubscription.status == 'active',
        UserSubscription.end_date > now,
        UserSubscription.end_date <= reminder_threshold
    ).all()
    
    reminded_count = 0
    for sub in expiring_soon_subs:
        # 在实际应用中，这里应该调用通知服务发送邮件/短信
        # 现在我们只记录日志
        days_until_expiry = (sub.end_date - now).days
        logger.info(f"Reminder: Subscription {sub.id} for user {sub.user_id} expires in {days_until_expiry} days")
        
        # 这里可以调用通知服务
        # notification_service.send_email(user_id=sub.user_id, template="subscription_expiring", ...)
        
        reminded_count += 1
    
    return {
        "reminded": reminded_count,
        "timestamp": now.isoformat()
    }


def process_quota_resets(db: Session) -> dict:
    """
    检查并重置到期的配额周期

    遍历所有活跃应用的配额配置，检查当前计费周期是否已结束。
    如果周期已结束：持久化当前周期使用数据到 QuotaUsage 表，重置 Redis 计数器，
    更新周期开始时间，记录审计日志（reset_type=auto）。

    这个函数应该由定时任务定期调用（如每小时一次）。

    返回：处理结果统计
    """
    now = datetime.utcnow()

    # 查询所有活跃应用及其订阅计划绑定
    app_bindings = (
        db.query(Application, AppSubscriptionPlan, SubscriptionPlan)
        .join(AppSubscriptionPlan, Application.id == AppSubscriptionPlan.application_id)
        .join(SubscriptionPlan, AppSubscriptionPlan.plan_id == SubscriptionPlan.id)
        .filter(Application.status == 'active')
        .all()
    )

    processed_count = 0
    reset_count = 0
    error_count = 0

    try:
        redis_client = get_redis()
    except Exception as e:
        logger.error(f"Redis 连接失败，配额重置无法执行: {e}")
        return {
            "processed": 0,
            "reset": 0,
            "errors": 1,
            "timestamp": now.isoformat(),
            "error_message": f"Redis 连接失败: {str(e)}"
        }

    for application, binding, plan in app_bindings:
        processed_count += 1
        app_id = application.app_id

        try:
            # 从 Redis 读取当前周期开始时间
            cycle_start_key = f"quota:{app_id}:cycle_start"
            cycle_start_str = redis_client.get(cycle_start_key)

            if not cycle_start_str:
                # 没有周期开始时间，跳过（可能尚未初始化）
                continue

            cycle_start = datetime.fromisoformat(cycle_start_str)
            quota_period_days = plan.quota_period_days or 30
            cycle_end = cycle_start + timedelta(days=quota_period_days)

            # 检查当前周期是否已结束
            if cycle_end > now:
                continue

            # --- 周期已结束，执行重置 ---

            # 1. 从 Redis 读取当前使用量
            requests_key = f"quota:{app_id}:requests"
            tokens_key = f"quota:{app_id}:tokens"

            request_used = int(redis_client.get(requests_key) or 0)
            token_used = int(float(redis_client.get(tokens_key) or 0))

            # 2. 计算有效配额（AppQuotaOverride 优先）
            override = db.query(AppQuotaOverride).filter(
                AppQuotaOverride.application_id == application.id
            ).first()

            effective_request_quota = plan.request_quota
            effective_token_quota = plan.token_quota
            if override:
                if override.request_quota is not None:
                    effective_request_quota = override.request_quota
                if override.token_quota is not None:
                    effective_token_quota = override.token_quota

            # 3. 持久化当前周期使用数据到 QuotaUsage 表
            usage_record = QuotaUsage(
                application_id=application.id,
                billing_cycle_start=cycle_start,
                billing_cycle_end=cycle_end,
                request_quota_limit=effective_request_quota,
                request_quota_used=request_used,
                token_quota_limit=effective_token_quota,
                token_quota_used=token_used,
                reset_type="auto"
            )
            db.add(usage_record)

            # 4. 重置 Redis 计数器
            new_cycle_start = now
            remaining_seconds = int(quota_period_days * 86400) + 86400  # TTL = 周期秒数 + 1天安全余量

            pipe = redis_client.pipeline()
            pipe.set(requests_key, 0, ex=remaining_seconds)
            pipe.set(tokens_key, 0, ex=remaining_seconds)
            pipe.set(cycle_start_key, new_cycle_start.isoformat(), ex=remaining_seconds)
            # 清除预警标记
            pipe.delete(f"quota:{app_id}:warning_sent:80")
            pipe.delete(f"quota:{app_id}:warning_sent:100")
            pipe.execute()

            # 5. 记录审计日志
            create_audit_log(
                db=db,
                user_id=None,
                action="quota_reset",
                resource_type="application",
                resource_id=application.id,
                details={
                    "reset_type": "auto",
                    "app_id": app_id,
                    "billing_cycle_start": cycle_start.isoformat(),
                    "billing_cycle_end": cycle_end.isoformat(),
                    "request_quota_used": request_used,
                    "token_quota_used": token_used,
                    "request_quota_limit": effective_request_quota,
                    "token_quota_limit": effective_token_quota,
                    "new_cycle_start": new_cycle_start.isoformat()
                }
            )

            reset_count += 1
            logger.info(
                f"Quota reset for app {app_id}: requests={request_used}/{effective_request_quota}, "
                f"tokens={token_used}/{effective_token_quota}, cycle={cycle_start.isoformat()}->{new_cycle_start.isoformat()}"
            )

        except Exception as e:
            error_count += 1
            logger.error(f"Error processing quota reset for app {app_id}: {e}")
            continue

    # Commit all QuotaUsage records
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit quota usage records: {e}")
        db.rollback()
        error_count += 1

    return {
        "processed": processed_count,
        "reset": reset_count,
        "errors": error_count,
        "timestamp": now.isoformat()
    }


@app.post("/api/v1/admin/subscriptions/process-quota-resets")
async def trigger_quota_reset_processing(db: Session = Depends(get_db)):
    """
    手动触发配额重置处理（管理员接口）

    这个接口用于测试或手动触发配额重置。
    在生产环境中，应该由定时任务自动调用 process_quota_resets 函数。
    """
    result = process_quota_resets(db)
    return result


@app.post("/api/v1/admin/subscriptions/process-expired")
async def trigger_expiration_processing(db: Session = Depends(get_db)):
    """
    手动触发订阅到期处理（管理员接口）
    
    这个接口用于测试或手动触发到期处理。
    在生产环境中，应该由定时任务自动调用 process_expired_subscriptions 函数。
    """
    result = process_expired_subscriptions(db)
    return result


@app.post("/api/v1/admin/subscriptions/send-reminders")
async def trigger_reminder_sending(db: Session = Depends(get_db)):
    """
    手动触发订阅到期提醒发送（管理员接口）
    
    这个接口用于测试或手动触发提醒发送。
    在生产环境中，应该由定时任务自动调用 send_expiration_reminders 函数。
    """
    result = send_expiration_reminders(db)
    return result

# Webhook event handler dispatch map
EVENT_HANDLERS = {
    "subscription.created": handle_subscription_created,
    "subscription.renewed": handle_subscription_renewed,
    "subscription.upgraded": handle_subscription_upgraded,
    "subscription.downgraded": handle_subscription_downgraded,
    "subscription.cancelled": handle_subscription_cancelled,
    "subscription.expired": handle_subscription_expired,
}


@app.post("/api/v1/webhooks/subscription")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    """接收并处理第三方订阅 Webhook 事件"""
    app_id_header = None
    event_id_for_log = None
    event_type_for_log = None

    try:
        # 1. Read raw request body bytes
        body = await request.body()

        # 2. Extract authentication headers
        app_id_header = request.headers.get("X-App-Id", "")
        signature = request.headers.get("X-Webhook-Signature", "")

        # 3. Verify webhook signature (raises 401/403 on failure)
        app_info = await verify_webhook_signature(app_id_header, signature, body, db)

        # 4. Parse body as JSON and validate with WebhookEventPayload schema
        try:
            body_json = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=422, detail="无效的 JSON 格式")

        try:
            payload = WebhookEventPayload(**body_json)
        except ValidationError as ve:
            # Convert Pydantic errors to JSON-serializable format
            errors = []
            for err in ve.errors():
                errors.append({
                    "loc": list(err.get("loc", [])),
                    "msg": str(err.get("msg", "")),
                    "type": str(err.get("type", "")),
                })
            raise HTTPException(status_code=422, detail=errors)

        event_id_for_log = payload.event_id
        event_type_for_log = payload.event_type.value

        # 5. Idempotency check: query WebhookEventLog by event_id
        existing_log = db.query(WebhookEventLog).filter(
            WebhookEventLog.event_id == payload.event_id
        ).first()

        if existing_log and existing_log.status in ("success", "duplicate"):
            # Record a duplicate log entry
            duplicate_log = WebhookEventLog(
                event_id=f"{payload.event_id}_dup_{datetime.utcnow().timestamp()}",
                app_id=app_id_header,
                event_type=event_type_for_log,
                status="duplicate",
                request_summary=body_json,
                response_summary=existing_log.response_summary,
                processed_at=datetime.utcnow(),
            )
            db.add(duplicate_log)
            db.commit()

            return JSONResponse(
                status_code=200,
                content={
                    "event_id": payload.event_id,
                    "status": "duplicate",
                    "original_result": existing_log.response_summary,
                },
            )

        # 6. Dispatch to appropriate handler based on event_type
        handler = EVENT_HANDLERS.get(event_type_for_log)
        if not handler:
            raise HTTPException(status_code=422, detail=f"不支持的事件类型: {event_type_for_log}")

        result = await handler(app_id_header, payload.data.model_dump(), db)

        # 7. Create WebhookEventLog record with status=success
        response_summary = {"event_id": payload.event_id, "status": "processed", "handler_result": result}
        event_log = WebhookEventLog(
            event_id=payload.event_id,
            app_id=app_id_header,
            event_type=event_type_for_log,
            status="success",
            request_summary=body_json,
            response_summary=response_summary,
            processed_at=datetime.utcnow(),
        )
        db.add(event_log)
        db.commit()

        # 8. Return 200 { event_id, status: "processed" }
        return JSONResponse(
            status_code=200,
            content={"event_id": payload.event_id, "status": "processed"},
        )

    except HTTPException:
        # Re-raise HTTP exceptions (401, 403, 422) as-is
        raise

    except Exception as exc:
        # 9. On any exception: create WebhookEventLog with status=failed, return 500
        error_msg = f"{type(exc).__name__}: {str(exc)}\n{traceback.format_exc()}"
        logger.error("Webhook processing error: %s", error_msg)

        try:
            failed_log = WebhookEventLog(
                event_id=event_id_for_log or f"unknown_{datetime.utcnow().timestamp()}",
                app_id=app_id_header or "unknown",
                event_type=event_type_for_log or "unknown",
                status="failed",
                error_message=error_msg,
                processed_at=datetime.utcnow(),
            )
            db.add(failed_log)
            db.commit()
        except Exception as log_exc:
            logger.error("Failed to record error event log: %s", str(log_exc))

        return JSONResponse(
            status_code=500,
            content={"error_code": "internal_error", "message": "内部服务器错误"},
        )

@app.get("/api/v1/webhooks/events")
async def list_webhook_events(
    app_id: Optional[str] = None,
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """分页查询 Webhook 事件日志"""
    query = db.query(WebhookEventLog)

    if app_id:
        query = query.filter(WebhookEventLog.app_id == app_id)
    if event_type:
        query = query.filter(WebhookEventLog.event_type == event_type)
    if status:
        query = query.filter(WebhookEventLog.status == status)
    if start_time:
        query = query.filter(WebhookEventLog.created_at >= start_time)
    if end_time:
        query = query.filter(WebhookEventLog.created_at <= end_time)

    total = query.count()

    offset = (page - 1) * page_size
    items = query.order_by(WebhookEventLog.created_at.desc()).offset(offset).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": str(item.id),
                "event_id": item.event_id,
                "app_id": item.app_id,
                "event_type": item.event_type,
                "status": item.status,
                "request_summary": item.request_summary,
                "response_summary": item.response_summary,
                "error_message": item.error_message,
                "processed_at": item.processed_at.isoformat() if item.processed_at else None,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
    }




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
