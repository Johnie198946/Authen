"""
订阅服务
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import json
import traceback
import hashlib
import hmac
import secrets
import uuid as uuid_lib
import httpx
from shared.database import get_db
from shared.models.subscription import (
    KnowledgePack,
    OrganizationKnowledgeGrant,
    OrganizationSubscription,
    OrganizationSubscriptionRequest,
    PlanKnowledgePackPolicy,
    SubscriptionPlan,
    UserSubscription,
)
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
    features: Optional[dict] = None

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


class OrganizationSubscriptionCreate(BaseModel):
    plan_id: str
    auto_renew: bool = True


class OrganizationSubscriptionResponse(BaseModel):
    id: str
    organization_id: str
    application_id: str
    plan_id: str
    status: str
    start_date: datetime
    end_date: datetime
    auto_renew: bool
    entitlement_version: int


class OrganizationRequestCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=160)
    plan_id: str
    requested_by: str
    requested_pack_ids: List[str] = Field(default_factory=list)
    requested_entitlements: List[str] = Field(default_factory=list)
    reason: str = ""


class OrganizationRequestReview(BaseModel):
    reviewed_by: str
    review_note: str = ""
    approved_pack_ids: Optional[List[str]] = None


def _require_bearer(request: Request, expected: str, purpose: str) -> None:
    if not expected:
        raise HTTPException(status_code=503, detail=f"{purpose} token is not configured")
    supplied = request.headers.get("authorization", "")
    if not supplied.startswith("Bearer ") or not secrets.compare_digest(supplied[7:], expected):
        raise HTTPException(status_code=403, detail="forbidden")


def require_subscription_admin(request: Request) -> None:
    _require_bearer(request, settings.SUBSCRIPTION_ADMIN_TOKEN, "subscription admin")


def require_ai_platform_service(request: Request) -> None:
    _require_bearer(request, settings.AI_PLATFORM_SERVICE_TOKEN, "AI Platform service")


def _knowledge_entitlements(plan: SubscriptionPlan) -> List[str]:
    features = plan.features if isinstance(plan.features, dict) else {}
    raw = features.get("knowledge_entitlements", [])
    if not isinstance(raw, list):
        return []
    result: List[str] = []
    for value in raw:
        key = str(value).strip()
        if key and "*" not in key and ".." not in key and "/" not in key and "\\" not in key:
            result.append(key)
    return sorted(set(result))


def _active_pack_grants(db: Session, sub: OrganizationSubscription) -> List[OrganizationKnowledgeGrant]:
    now = datetime.utcnow()
    return db.query(OrganizationKnowledgeGrant).join(
        KnowledgePack, KnowledgePack.id == OrganizationKnowledgeGrant.knowledge_pack_id
    ).filter(
        OrganizationKnowledgeGrant.organization_subscription_id == sub.id,
        OrganizationKnowledgeGrant.status == "active",
        OrganizationKnowledgeGrant.effective_until > now,
        KnowledgePack.status.in_(["published", "maintenance"]),
    ).all()


def _effective_entitlements(db: Session, sub: OrganizationSubscription) -> List[str]:
    if sub.status != "active" or sub.end_date <= datetime.utcnow():
        return []
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == sub.plan_id).first()
    result = set(_knowledge_entitlements(plan)) if plan else set()
    result.update(
        grant.knowledge_pack.entitlement_key
        for grant in _active_pack_grants(db, sub)
        if grant.knowledge_pack and grant.knowledge_pack.entitlement_key
    )
    return sorted(result)


def _pack_response(pack: KnowledgePack) -> dict:
    return {
        "id": str(pack.id),
        "entitlement_key": pack.entitlement_key,
        "name": pack.name,
        "description": pack.description,
        "status": pack.status,
        "is_selectable": bool(pack.is_selectable),
        "sort_order": pack.sort_order,
        "minimum_document_count": pack.minimum_document_count,
        "approved_document_count": pack.approved_document_count,
        "freshness_percent": pack.freshness_percent,
        "risk_label": pack.risk_label,
    }


def _grant_response(grant: OrganizationKnowledgeGrant) -> dict:
    return {
        "id": str(grant.id),
        "knowledge_pack_id": str(grant.knowledge_pack_id),
        "entitlement_key": grant.knowledge_pack.entitlement_key if grant.knowledge_pack else "",
        "name": grant.knowledge_pack.name if grant.knowledge_pack else "",
        "status": grant.status,
        "effective_from": grant.effective_from.isoformat(),
        "effective_until": grant.effective_until.isoformat(),
    }


def _request_response(item: OrganizationSubscriptionRequest) -> dict:
    return {
        "id": str(item.id),
        "request_id": item.request_id,
        "organization_id": str(item.organization_id),
        "application_id": str(item.application_id),
        "target_plan_id": str(item.target_plan_id),
        "target_plan_name": item.target_plan.name if item.target_plan else "",
        "requested_by": item.requested_by,
        "requested_pack_ids": item.requested_pack_ids or [],
        "requested_entitlements": item.requested_entitlements or [],
        "approved_pack_ids": item.approved_pack_ids or [],
        "reason": item.reason,
        "status": item.status,
        "reviewed_by": item.reviewed_by,
        "review_note": item.review_note,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _application(db: Session, app_id: str) -> Application:
    app_row = db.query(Application).filter(
        Application.app_id == app_id, Application.status == "active"
    ).first()
    if not app_row:
        raise HTTPException(status_code=404, detail="application not found")
    return app_row


def _bound_plan(db: Session, app: Application, plan_id: str) -> SubscriptionPlan:
    try:
        plan_uuid = uuid_lib.UUID(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid plan id") from exc
    plan = db.query(SubscriptionPlan).join(
        AppSubscriptionPlan, AppSubscriptionPlan.plan_id == SubscriptionPlan.id
    ).filter(
        SubscriptionPlan.id == plan_uuid,
        SubscriptionPlan.is_active == True,
        AppSubscriptionPlan.application_id == app.id,
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="subscription plan not found")
    return plan


def _pack_policy(db: Session, app: Application, plan: SubscriptionPlan) -> PlanKnowledgePackPolicy:
    policy = db.query(PlanKnowledgePackPolicy).filter(
        PlanKnowledgePackPolicy.plan_id == plan.id,
        PlanKnowledgePackPolicy.application_id == app.id,
    ).first()
    if policy is None:
        raise HTTPException(status_code=409, detail="plan knowledge-pack policy is not configured")
    return policy


def _validated_packs(
    db: Session, app: Application, policy: PlanKnowledgePackPolicy, raw_ids: List[str]
) -> List[KnowledgePack]:
    if policy.custom_only:
        raise HTTPException(
            status_code=422,
            detail="custom plan requires administrator configuration",
        )
    try:
        ids = list(dict.fromkeys(uuid_lib.UUID(value) for value in raw_ids))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="invalid knowledge pack id") from exc
    if policy.max_pack_count >= 0 and len(ids) > policy.max_pack_count:
        raise HTTPException(status_code=422, detail="knowledge pack allowance exceeded")
    allowed = {str(value) for value in (policy.selectable_pack_ids or [])}
    if any(str(value) not in allowed for value in ids):
        raise HTTPException(status_code=422, detail="knowledge pack is not allowed by target plan")
    packs = db.query(KnowledgePack).filter(
        KnowledgePack.id.in_(ids), KnowledgePack.application_id == app.id
    ).all() if ids else []
    by_id = {pack.id: pack for pack in packs}
    if len(by_id) != len(ids):
        raise HTTPException(status_code=422, detail="knowledge pack not found")
    ordered = [by_id[value] for value in ids]
    if any(
        pack.status != "published"
        or not pack.is_selectable
        or pack.approved_document_count < pack.minimum_document_count
        or pack.freshness_percent < 80
        for pack in ordered
    ):
        raise HTTPException(status_code=422, detail="knowledge pack governance is not complete")
    return ordered


def _validate_plan_features(features: Optional[dict]) -> None:
    if features is None:
        return
    values = features.get("knowledge_entitlements", [])
    if not isinstance(values, list) or any(
        not isinstance(value, str)
        or not value.strip()
        or any(part in value for part in ("*", "..", "/", "\\"))
        for value in values
    ):
        raise HTTPException(
            status_code=422,
            detail="knowledge_entitlements must contain exact category IDs without paths or wildcards",
        )


def _plan_response(plan: SubscriptionPlan) -> PlanResponse:
    return PlanResponse(
        id=str(plan.id), name=plan.name, description=plan.description,
        duration_days=plan.duration_days, price=float(plan.price), is_active=plan.is_active,
        request_quota=plan.request_quota, token_quota=plan.token_quota,
        quota_period_days=plan.quota_period_days, features=plan.features,
    )


def _organization_subscription_response(sub: OrganizationSubscription) -> OrganizationSubscriptionResponse:
    return OrganizationSubscriptionResponse(
        id=str(sub.id), organization_id=str(sub.organization_id), application_id=str(sub.application_id),
        plan_id=str(sub.plan_id), status=sub.status, start_date=sub.start_date, end_date=sub.end_date,
        auto_renew=sub.auto_renew, entitlement_version=sub.entitlement_version,
    )


async def _push_entitlement_changed(sub_id: str) -> None:
    """Best-effort projection update; the platform also performs periodic reconciliation."""
    if not settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_URL or not settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_SECRET:
        return
    db = next(get_db())
    try:
        sub = db.query(OrganizationSubscription).filter(OrganizationSubscription.id == uuid_lib.UUID(sub_id)).first()
        if not sub:
            return
        app = db.query(Application).filter(Application.id == sub.application_id).first()
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == sub.plan_id).first()
        if not app or not plan:
            return
        policy = db.query(PlanKnowledgePackPolicy).filter(
            PlanKnowledgePackPolicy.plan_id == sub.plan_id,
            PlanKnowledgePackPolicy.application_id == sub.application_id,
        ).first()
        payload: Dict[str, Any] = {
            "event_id": f"entitlement:{sub.id}:{sub.entitlement_version}",
            "event_type": "entitlement.changed",
            "organization_id": str(sub.organization_id),
            "application_id": app.app_id,
            "plan_id": str(plan.id),
            "status": sub.status,
            "effective_until": sub.end_date.isoformat(),
            "knowledge_entitlements": _effective_entitlements(db, sub),
            "active_pack_grants": [
                _grant_response(grant) for grant in _active_pack_grants(db, sub)
            ],
            "pack_allowance": policy.max_pack_count if policy else 0,
            "request_quota": plan.request_quota,
            "token_quota": plan.token_quota,
            "entitlement_version": sub.entitlement_version,
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        signature = hmac.new(
            settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_URL,
                content=body,
                headers={"content-type": "application/json", "x-webhook-signature": signature},
            )
            response.raise_for_status()
    except Exception as exc:
        logger.warning("entitlement.changed delivery failed for %s: %s", sub_id, exc)
    finally:
        db.close()

@app.get("/")
async def root():
    return {"service": "订阅服务", "status": "running"}


@app.get("/api/v1/internal/plans")
async def internal_list_plans(
    app_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_ai_platform_service),
):
    app_row = _application(db, app_id)
    rows = db.query(SubscriptionPlan, PlanKnowledgePackPolicy).join(
        AppSubscriptionPlan, AppSubscriptionPlan.plan_id == SubscriptionPlan.id
    ).join(
        PlanKnowledgePackPolicy,
        (PlanKnowledgePackPolicy.plan_id == SubscriptionPlan.id)
        & (PlanKnowledgePackPolicy.application_id == app_row.id),
    ).filter(
        AppSubscriptionPlan.application_id == app_row.id,
        SubscriptionPlan.is_active == True,
    ).order_by(SubscriptionPlan.request_quota.asc()).all()
    plans = []
    for plan, policy in rows:
        item = _plan_response(plan).dict()
        item.update({
            "pack_allowance": policy.max_pack_count,
            "custom_only": policy.custom_only,
            "selectable_pack_ids": policy.selectable_pack_ids or [],
        })
        plans.append(item)
    return {"application_id": app_id, "plans": plans}


@app.get("/api/v1/internal/organizations/{org_id}/subscription-center")
async def organization_subscription_center(
    org_id: str,
    app_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_ai_platform_service),
):
    try:
        org_uuid = uuid_lib.UUID(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid organization id") from exc
    app_row = _application(db, app_id)
    sub = db.query(OrganizationSubscription).filter(
        OrganizationSubscription.organization_id == org_uuid,
        OrganizationSubscription.application_id == app_row.id,
    ).first()
    requests = db.query(OrganizationSubscriptionRequest).filter(
        OrganizationSubscriptionRequest.organization_id == org_uuid,
        OrganizationSubscriptionRequest.application_id == app_row.id,
    ).order_by(OrganizationSubscriptionRequest.created_at.desc()).limit(20).all()
    packs = db.query(KnowledgePack).filter(
        KnowledgePack.application_id == app_row.id,
        KnowledgePack.status != "retired",
    ).order_by(KnowledgePack.sort_order.asc()).all()
    current = None
    active_grants: List[dict] = []
    allowance = 0
    if sub is not None:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == sub.plan_id).first()
        policy = db.query(PlanKnowledgePackPolicy).filter(
            PlanKnowledgePackPolicy.plan_id == sub.plan_id,
            PlanKnowledgePackPolicy.application_id == app_row.id,
        ).first()
        allowance = policy.max_pack_count if policy else 0
        active_grants = [_grant_response(grant) for grant in _active_pack_grants(db, sub)]
        current = {
            "id": str(sub.id),
            "plan_id": str(sub.plan_id),
            "plan_name": plan.name if plan else "",
            "status": sub.status,
            "start_date": sub.start_date.isoformat(),
            "effective_until": sub.end_date.isoformat(),
            "entitlement_version": sub.entitlement_version,
            "knowledge_entitlements": _effective_entitlements(db, sub),
            "pack_allowance": allowance,
            "active_pack_grants": active_grants,
        }
    return {
        "organization_id": org_id,
        "application_id": app_id,
        "subscription": current,
        "requests": [_request_response(item) for item in requests],
        "knowledge_packs": [_pack_response(pack) for pack in packs],
        "active_pack_grants": active_grants,
        "pack_allowance": allowance,
    }


@app.post("/api/v1/internal/organizations/{org_id}/subscription-requests")
async def create_organization_subscription_request(
    org_id: str,
    app_id: str,
    body: OrganizationRequestCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_ai_platform_service),
):
    try:
        org_uuid = uuid_lib.UUID(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid organization id") from exc
    app_row = _application(db, app_id)
    plan = _bound_plan(db, app_row, body.plan_id)
    existing = db.query(OrganizationSubscriptionRequest).filter(
        OrganizationSubscriptionRequest.request_id == body.request_id
    ).first()
    if existing is not None:
        if existing.organization_id != org_uuid or existing.application_id != app_row.id:
            raise HTTPException(status_code=409, detail="request_id already used")
        return _request_response(existing)
    pending = db.query(OrganizationSubscriptionRequest).filter(
        OrganizationSubscriptionRequest.organization_id == org_uuid,
        OrganizationSubscriptionRequest.application_id == app_row.id,
        OrganizationSubscriptionRequest.status == "pending",
    ).first()
    if pending is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "request_pending", "request": _request_response(pending)},
        )
    policy = _pack_policy(db, app_row, plan)
    requested_ids = list(body.requested_pack_ids)
    if body.requested_entitlements:
        legacy_packs = db.query(KnowledgePack).filter(
            KnowledgePack.application_id == app_row.id,
            KnowledgePack.entitlement_key.in_(body.requested_entitlements),
        ).all()
        if len({pack.entitlement_key for pack in legacy_packs}) != len(set(body.requested_entitlements)):
            raise HTTPException(status_code=422, detail="requested entitlement is not a knowledge pack")
        requested_ids.extend(str(pack.id) for pack in legacy_packs)
    packs = _validated_packs(db, app_row, policy, requested_ids)
    item = OrganizationSubscriptionRequest(
        request_id=body.request_id,
        organization_id=org_uuid,
        application_id=app_row.id,
        target_plan_id=plan.id,
        requested_by=body.requested_by,
        requested_pack_ids=[str(pack.id) for pack in packs],
        requested_entitlements=[pack.entitlement_key for pack in packs],
        reason=body.reason.strip(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _request_response(item)


@app.delete("/api/v1/internal/organizations/{org_id}/subscription-requests/{request_id}")
async def cancel_organization_subscription_request(
    org_id: str,
    request_id: str,
    app_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_ai_platform_service),
):
    try:
        org_uuid = uuid_lib.UUID(org_id)
        request_uuid = uuid_lib.UUID(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid id") from exc
    app_row = _application(db, app_id)
    item = db.query(OrganizationSubscriptionRequest).filter(
        OrganizationSubscriptionRequest.id == request_uuid,
        OrganizationSubscriptionRequest.organization_id == org_uuid,
        OrganizationSubscriptionRequest.application_id == app_row.id,
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="subscription request not found")
    if item.status != "pending":
        raise HTTPException(status_code=409, detail="only pending request can be cancelled")
    item.status = "cancelled"
    db.commit()
    db.refresh(item)
    return _request_response(item)


@app.get("/api/v1/internal/admin/subscription-requests")
async def admin_list_subscription_requests(
    app_id: str,
    status: str = "pending",
    db: Session = Depends(get_db),
    _: None = Depends(require_ai_platform_service),
):
    app_row = _application(db, app_id)
    query = db.query(OrganizationSubscriptionRequest).filter(
        OrganizationSubscriptionRequest.application_id == app_row.id
    )
    if status:
        query = query.filter(OrganizationSubscriptionRequest.status == status)
    items = query.order_by(OrganizationSubscriptionRequest.created_at.desc()).limit(200).all()
    return {"application_id": app_id, "requests": [_request_response(item) for item in items]}


async def _review_organization_request(
    *, request_id: str, app_id: str, approve: bool, review: OrganizationRequestReview,
    background_tasks: BackgroundTasks, db: Session,
) -> dict:
    try:
        request_uuid = uuid_lib.UUID(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid request id") from exc
    app_row = _application(db, app_id)
    item = db.query(OrganizationSubscriptionRequest).filter(
        OrganizationSubscriptionRequest.id == request_uuid,
        OrganizationSubscriptionRequest.application_id == app_row.id,
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="subscription request not found")
    if item.status != "pending":
        return {**_request_response(item), "webhook_delivered": None}
    item.status = "approved" if approve else "rejected"
    item.reviewed_by = review.reviewed_by
    item.review_note = review.review_note.strip()
    item.reviewed_at = datetime.utcnow()
    sub = None
    if approve:
        policy = _pack_policy(db, app_row, item.target_plan)
        approved_ids = (
            review.approved_pack_ids
            if review.approved_pack_ids is not None
            else list(item.requested_pack_ids or [])
        )
        requested = set(item.requested_pack_ids or [])
        if not set(approved_ids).issubset(requested):
            raise HTTPException(status_code=422, detail="approved packs must be a subset of requested packs")
        approved_packs = _validated_packs(db, app_row, policy, approved_ids)
        now = datetime.utcnow()
        sub = db.query(OrganizationSubscription).filter(
            OrganizationSubscription.organization_id == item.organization_id,
            OrganizationSubscription.application_id == app_row.id,
        ).first()
        if sub is None:
            sub = OrganizationSubscription(
                organization_id=item.organization_id,
                application_id=app_row.id,
                plan_id=item.target_plan_id,
                status="active",
                start_date=now,
                end_date=now + timedelta(days=item.target_plan.duration_days),
                auto_renew=True,
                entitlement_version=1,
            )
            db.add(sub)
            db.flush()
        else:
            sub.plan_id = item.target_plan_id
            sub.status = "active"
            sub.start_date = now
            sub.end_date = now + timedelta(days=item.target_plan.duration_days)
            sub.auto_renew = True
            sub.entitlement_version += 1
        selected_ids = {pack.id for pack in approved_packs}
        existing_grants = db.query(OrganizationKnowledgeGrant).filter(
            OrganizationKnowledgeGrant.organization_subscription_id == sub.id
        ).all()
        by_pack = {grant.knowledge_pack_id: grant for grant in existing_grants}
        for grant in existing_grants:
            if grant.knowledge_pack_id not in selected_ids and grant.status == "active":
                grant.status = "revoked"
                grant.revoked_at = now
        for pack in approved_packs:
            grant = by_pack.get(pack.id)
            if grant is None:
                grant = OrganizationKnowledgeGrant(
                    organization_subscription_id=sub.id,
                    knowledge_pack_id=pack.id,
                    effective_from=now,
                    effective_until=sub.end_date,
                    approved_by=review.reviewed_by,
                    source_request_id=item.request_id,
                )
                db.add(grant)
            else:
                grant.status = "active"
                grant.effective_from = now
                grant.effective_until = sub.end_date
                grant.approved_by = review.reviewed_by
                grant.source_request_id = item.request_id
                grant.revoked_at = None
        item.approved_pack_ids = [str(pack.id) for pack in approved_packs]
    db.commit()
    db.refresh(item)
    delivered = None
    if sub is not None:
        background_tasks.add_task(_push_entitlement_changed, str(sub.id))
        delivered = bool(
            settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_URL
            and settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_SECRET
        )
    return {**_request_response(item), "webhook_delivered": delivered}


@app.post("/api/v1/internal/admin/subscription-requests/{request_id}/approve")
async def approve_subscription_request(
    request_id: str, body: OrganizationRequestReview, background_tasks: BackgroundTasks,
    app_id: str, db: Session = Depends(get_db),
    _: None = Depends(require_ai_platform_service),
):
    return await _review_organization_request(
        request_id=request_id, app_id=app_id, approve=True, review=body,
        background_tasks=background_tasks, db=db,
    )


@app.post("/api/v1/internal/admin/subscription-requests/{request_id}/reject")
async def reject_subscription_request(
    request_id: str, body: OrganizationRequestReview, background_tasks: BackgroundTasks,
    app_id: str, db: Session = Depends(get_db),
    _: None = Depends(require_ai_platform_service),
):
    return await _review_organization_request(
        request_id=request_id, app_id=app_id, approve=False, review=body,
        background_tasks=background_tasks, db=db,
    )

@app.get("/api/v1/subscriptions/plans", response_model=List[PlanResponse])
async def list_plans(db: Session = Depends(get_db)):
    """获取订阅计划列表"""
    plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).all()
    return [_plan_response(p) for p in plans]

@app.post("/api/v1/subscriptions/plans", response_model=PlanResponse)
async def create_plan(plan_data: PlanCreate, db: Session = Depends(get_db), _: None = Depends(require_subscription_admin)):
    """创建订阅计划"""
    _validate_plan_features(plan_data.features)
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
    return _plan_response(plan)

@app.put("/api/v1/subscriptions/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(plan_id: str, plan_data: PlanCreate, db: Session = Depends(get_db), _: None = Depends(require_subscription_admin)):
    """更新订阅计划"""
    import uuid as uuid_lib
    try:
        plan_uuid = uuid_lib.UUID(plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的计划ID")
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_uuid).first()
    if not plan:
        raise HTTPException(status_code=404, detail="订阅计划不存在")
    _validate_plan_features(plan_data.features)
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
    return _plan_response(plan)

@app.delete("/api/v1/subscriptions/plans/{plan_id}")
async def delete_plan(plan_id: str, db: Session = Depends(get_db), _: None = Depends(require_subscription_admin)):
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
async def get_user_subscription(user_id: str, db: Session = Depends(get_db), _: None = Depends(require_subscription_admin)):
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
async def create_subscription(user_id: str, sub_data: SubscriptionCreate, db: Session = Depends(get_db), _: None = Depends(require_subscription_admin)):
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
async def cancel_subscription(user_id: str, db: Session = Depends(get_db), _: None = Depends(require_subscription_admin)):
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


@app.get(
    "/api/v1/internal/organizations/{org_id}/entitlements",
)
async def get_organization_entitlements(
    org_id: str,
    app_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_ai_platform_service),
):
    """Return the effective organization entitlement projection to AI Platform only."""
    try:
        org_uuid = uuid_lib.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid organization id")
    app = db.query(Application).filter(Application.app_id == app_id, Application.status == "active").first()
    if not app:
        raise HTTPException(status_code=404, detail="application not found")
    sub = db.query(OrganizationSubscription).filter(
        OrganizationSubscription.organization_id == org_uuid,
        OrganizationSubscription.application_id == app.id,
    ).first()
    if not sub:
        return {
            "organization_id": org_id, "application_id": app_id, "plan_id": None,
            "status": "none", "effective_until": None, "knowledge_entitlements": [],
            "request_quota": 0, "token_quota": 0, "entitlement_version": 0,
        }
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == sub.plan_id).first()
    now = datetime.utcnow()
    effective_status = sub.status
    if effective_status == "active" and sub.end_date <= now:
        effective_status = "expired"
    pack_policy = db.query(PlanKnowledgePackPolicy).filter(
        PlanKnowledgePackPolicy.plan_id == sub.plan_id,
        PlanKnowledgePackPolicy.application_id == app.id,
    ).first()
    return {
        "organization_id": org_id,
        "application_id": app_id,
        "plan_id": str(plan.id) if plan else None,
        "plan_name": plan.name if plan else None,
        "status": effective_status,
        "effective_until": sub.end_date.isoformat(),
        "knowledge_entitlements": _effective_entitlements(db, sub) if effective_status == "active" else [],
        "active_pack_grants": [
            _grant_response(grant) for grant in _active_pack_grants(db, sub)
        ] if effective_status == "active" else [],
        "pack_allowance": pack_policy.max_pack_count if pack_policy else 0,
        "request_quota": plan.request_quota if plan else 0,
        "token_quota": plan.token_quota if plan else 0,
        "entitlement_version": sub.entitlement_version,
    }


@app.put(
    "/api/v1/admin/organizations/{org_id}/subscriptions/{app_id}",
    response_model=OrganizationSubscriptionResponse,
)
async def upsert_organization_subscription(
    org_id: str,
    app_id: str,
    data: OrganizationSubscriptionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: None = Depends(require_subscription_admin),
):
    try:
        org_uuid = uuid_lib.UUID(org_id)
        plan_uuid = uuid_lib.UUID(data.plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid id")
    app = db.query(Application).filter(Application.app_id == app_id, Application.status == "active").first()
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_uuid, SubscriptionPlan.is_active == True).first()
    if not app or not plan:
        raise HTTPException(status_code=404, detail="application or plan not found")
    allowed = db.query(AppSubscriptionPlan).filter(
        AppSubscriptionPlan.application_id == app.id,
        AppSubscriptionPlan.plan_id == plan.id,
    ).first()
    if not allowed:
        raise HTTPException(status_code=400, detail="plan is not bound to application")
    now = datetime.utcnow()
    sub = db.query(OrganizationSubscription).filter(
        OrganizationSubscription.organization_id == org_uuid,
        OrganizationSubscription.application_id == app.id,
    ).first()
    if sub:
        sub.plan_id = plan.id
        sub.status = "active"
        sub.start_date = now
        sub.end_date = now + timedelta(days=plan.duration_days)
        sub.auto_renew = data.auto_renew
        sub.entitlement_version += 1
    else:
        sub = OrganizationSubscription(
            organization_id=org_uuid, application_id=app.id, plan_id=plan.id,
            status="active", start_date=now, end_date=now + timedelta(days=plan.duration_days),
            auto_renew=data.auto_renew, entitlement_version=1,
        )
        db.add(sub)
    db.commit()
    db.refresh(sub)
    background_tasks.add_task(_push_entitlement_changed, str(sub.id))
    return _organization_subscription_response(sub)


@app.delete("/api/v1/admin/organizations/{org_id}/subscriptions/{app_id}")
async def cancel_organization_subscription(
    org_id: str,
    app_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: None = Depends(require_subscription_admin),
):
    try:
        org_uuid = uuid_lib.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid organization id")
    app = db.query(Application).filter(Application.app_id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="application not found")
    sub = db.query(OrganizationSubscription).filter(
        OrganizationSubscription.organization_id == org_uuid,
        OrganizationSubscription.application_id == app.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="organization subscription not found")
    sub.status = "cancelled"
    sub.auto_renew = False
    sub.entitlement_version += 1
    db.commit()
    background_tasks.add_task(_push_entitlement_changed, str(sub.id))
    return {"success": True, "entitlement_version": sub.entitlement_version}


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

    expired_org_subs = db.query(OrganizationSubscription).filter(
        OrganizationSubscription.status == "active",
        OrganizationSubscription.end_date <= now,
    ).all()
    changed_org_ids: List[str] = []
    for sub in expired_org_subs:
        sub.status = "expired"
        sub.auto_renew = False
        sub.entitlement_version += 1
        sub.updated_at = now
        changed_org_ids.append(str(sub.id))
    
    db.commit()
    
    return {
        "processed": processed_count,
        "timestamp": now.isoformat(),
        "organization_subscription_ids": changed_org_ids,
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
async def trigger_quota_reset_processing(db: Session = Depends(get_db), _: None = Depends(require_subscription_admin)):
    """
    手动触发配额重置处理（管理员接口）

    这个接口用于测试或手动触发配额重置。
    在生产环境中，应该由定时任务自动调用 process_quota_resets 函数。
    """
    result = process_quota_resets(db)
    return result


@app.post("/api/v1/admin/subscriptions/process-expired")
async def trigger_expiration_processing(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: None = Depends(require_subscription_admin),
):
    """
    手动触发订阅到期处理（管理员接口）
    
    这个接口用于测试或手动触发到期处理。
    在生产环境中，应该由定时任务自动调用 process_expired_subscriptions 函数。
    """
    result = process_expired_subscriptions(db)
    for sub_id in result.pop("organization_subscription_ids", []):
        background_tasks.add_task(_push_entitlement_changed, sub_id)
    return result


@app.post("/api/v1/admin/subscriptions/send-reminders")
async def trigger_reminder_sending(db: Session = Depends(get_db), _: None = Depends(require_subscription_admin)):
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
