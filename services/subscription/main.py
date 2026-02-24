"""
订阅服务
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timedelta
from shared.database import get_db
from shared.models.subscription import SubscriptionPlan, UserSubscription
from shared.config import settings
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

class PlanResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    duration_days: int
    price: float
    is_active: bool

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
    return [PlanResponse(id=str(p.id), name=p.name, description=p.description, duration_days=p.duration_days, price=float(p.price), is_active=p.is_active) for p in plans]

@app.post("/api/v1/subscriptions/plans", response_model=PlanResponse)
async def create_plan(plan_data: PlanCreate, db: Session = Depends(get_db)):
    """创建订阅计划"""
    plan = SubscriptionPlan(name=plan_data.name, description=plan_data.description, duration_days=plan_data.duration_days, price=plan_data.price, features=plan_data.features)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return PlanResponse(id=str(plan.id), name=plan.name, description=plan.description, duration_days=plan.duration_days, price=float(plan.price), is_active=plan.is_active)

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
    plan.name = plan_data.name
    plan.description = plan_data.description
    plan.duration_days = plan_data.duration_days
    plan.price = plan_data.price
    if plan_data.features is not None:
        plan.features = plan_data.features
    db.commit()
    db.refresh(plan)
    return PlanResponse(id=str(plan.id), name=plan.name, description=plan.description, duration_days=plan.duration_days, price=float(plan.price), is_active=plan.is_active)

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
