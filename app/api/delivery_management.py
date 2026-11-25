import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_delivery_partner
from app.core.rate_limit import limiter
from app.core.tokens import create_access_token, create_refresh_token
from app.models.user import User
from app.models.order import Order, OrderStatus
from app.models.delivery_management import DeliveryPartnerProfile, DeliveryAssignment, DeliveryAssignmentHistory
from app.schemas.auth import AdminLogin, TokenResponse
from app.schemas.delivery_management import DeliveryActionIn, DeliveryAssignmentOut, DeliveryOrderOut
from app.services.auth_service import authenticate_delivery_partner
from app.services.order_service import transition_order_status

auth_router = APIRouter(prefix="/delivery/auth", tags=["delivery-auth"])
router = APIRouter(prefix="/delivery", tags=["delivery-partner"])
ACTIVE = ("assigned", "accepted", "picked_up", "in_progress")


@auth_router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def partner_login(request: Request, data: AdminLogin, db: AsyncSession = Depends(get_db)):
    user = await authenticate_delivery_partner(db, data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid delivery partner credentials")
    return TokenResponse(access_token=create_access_token(str(user.id), "delivery_partner"),
        expires_in=30 * 60, refresh_token=create_refresh_token(str(user.id), "delivery_partner"))


async def get_assignment(db: AsyncSession, order_id: uuid.UUID, partner: User, *, lock: bool = False):
    stmt = select(DeliveryAssignment).where(DeliveryAssignment.order_id == order_id,
        DeliveryAssignment.partner_id == partner.id, DeliveryAssignment.status.in_(ACTIVE))
    if lock:
        stmt = stmt.with_for_update()
    assignment = (await db.execute(stmt)).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Active delivery assignment not found")
    return assignment


async def delivery_order(db: AsyncSession, order_id: uuid.UUID, partner: User, lock: bool = False):
    assignment = await get_assignment(db, order_id, partner, lock=lock)
    stmt = select(Order).where(Order.id == order_id)
    if lock:
        stmt = stmt.with_for_update()
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Assigned order not found")
    assignment.order_number = order.order_number
    assignment.fulfillment_status = order.status.value
    return order, assignment


@router.get("/profile")
async def profile(db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    profile = await db.get(DeliveryPartnerProfile, partner.id)
    return {"user_id": str(partner.id), "employee_id": profile.employee_id, "full_name": partner.full_name,
        "phone": partner.phone, "availability": profile.availability, "is_active": partner.is_active,
        "service_area": profile.service_area, "max_active_deliveries": profile.max_active_deliveries}


@router.patch("/availability")
async def set_availability(availability: str, db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    if availability not in ("available", "offline"):
        raise HTTPException(status_code=422, detail="Availability must be available or offline")
    profile = await db.get(DeliveryPartnerProfile, partner.id, with_for_update=True)
    profile.availability = availability
    return {"availability": profile.availability}


@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    profile = await db.get(DeliveryPartnerProfile, partner.id)
    counts = {}
    for state in ("assigned", "accepted", "picked_up", "in_progress", "completed", "failed"):
        counts[state] = await db.scalar(select(func.count()).select_from(DeliveryAssignment).where(
            DeliveryAssignment.partner_id == partner.id, DeliveryAssignment.status == state)) or 0
    active = list((await db.execute(select(DeliveryAssignment).where(
        DeliveryAssignment.partner_id == partner.id, DeliveryAssignment.status.in_(ACTIVE)).order_by(DeliveryAssignment.assigned_at.desc()).limit(20))).scalars().all())
    order_ids = [a.order_id for a in active]
    order_map = {o.id: o for o in (await db.execute(select(Order).where(Order.id.in_(order_ids)))).scalars().all()} if order_ids else {}
    items = []
    for assignment in active:
        order = order_map.get(assignment.order_id)
        if order:
            assignment.order_number = order.order_number
            assignment.fulfillment_status = order.status.value
            items.append(assignment)
    return {"counts": counts, "availability": profile.availability, "active_deliveries": items}


@router.get("/orders", response_model=list[DeliveryOrderOut])
async def list_assigned_orders(db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    assignments = list((await db.execute(select(DeliveryAssignment).where(
        DeliveryAssignment.partner_id == partner.id, DeliveryAssignment.status.in_(ACTIVE)).order_by(DeliveryAssignment.assigned_at.desc()))).scalars().all())
    result = []
    for assignment in assignments:
        order = (await db.execute(select(Order).where(Order.id == assignment.order_id))).scalar_one_or_none()
        if order:
            assignment.order_number = order.order_number
            assignment.fulfillment_status = order.status.value
            result.append({"id": order.id, "order_number": order.order_number, "status": order.status.value,
                "payment_method": order.payment_method.value, "payment_status": order.payment_status.value,
                "shipping_name": order.shipping_name, "shipping_phone": order.shipping_phone,
                "shipping_line1": order.shipping_line1, "shipping_line2": order.shipping_line2,
                "shipping_landmark": order.shipping_landmark, "shipping_city": order.shipping_city,
                "shipping_state": order.shipping_state, "shipping_pincode": order.shipping_pincode,
                "notes": order.notes, "total_paise": order.total_paise,
                "amount_paid_paise": order.amount_paid_paise, "outstanding_amount_paise": order.outstanding_paise,
                "created_at": order.created_at, "items": order.items, "assignment": assignment})
    return result


@router.get("/orders/{order_id}", response_model=DeliveryOrderOut)
async def get_assigned_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    order, assignment = await delivery_order(db, order_id, partner)
    return {"id": order.id, "order_number": order.order_number, "status": order.status.value,
        "payment_method": order.payment_method.value, "payment_status": order.payment_status.value,
        "shipping_name": order.shipping_name, "shipping_phone": order.shipping_phone,
        "shipping_line1": order.shipping_line1, "shipping_line2": order.shipping_line2,
        "shipping_landmark": order.shipping_landmark, "shipping_city": order.shipping_city,
        "shipping_state": order.shipping_state, "shipping_pincode": order.shipping_pincode,
        "notes": order.notes, "total_paise": order.total_paise, "amount_paid_paise": order.amount_paid_paise,
        "outstanding_amount_paise": order.outstanding_paise, "created_at": order.created_at,
        "items": order.items, "assignment": assignment}


async def update_assignment(order_id: uuid.UUID, data: DeliveryActionIn, partner: User, db: AsyncSession, action: str):
    order, assignment = await delivery_order(db, order_id, partner, lock=True)
    if data.expected_version != assignment.version:
        raise HTTPException(status_code=409, detail=f"Assignment changed concurrently (current version {assignment.version}); refresh and retry")
    transitions = {
        "accept": ("assigned", "accepted"), "reject": ("assigned", "rejected"),
        "pickup": ("accepted", "picked_up"), "start": ("picked_up", "in_progress"),
        "failed": ("in_progress", "failed"),
    }
    expected, target = transitions[action]
    if assignment.status != expected:
        raise HTTPException(status_code=409, detail=f"Cannot {action} assignment in '{assignment.status}' state")
    now = datetime.now(timezone.utc)
    if action == "pickup":
        if order.status == OrderStatus.packed:
            ok, err = await transition_order_status(db, order, "shipped", changed_by=partner.id,
                note=data.note or "Parcel picked up by delivery partner", expected_version=order.version,
                actor_type="delivery_partner")
            if not ok:
                raise HTTPException(status_code=409, detail=err)
        elif order.status != OrderStatus.delivery_failed:
            raise HTTPException(status_code=409, detail="Parcel pickup requires a packed or rescheduled failed order")
        assignment.picked_up_at = now
    elif action == "start":
        if order.status not in (OrderStatus.shipped, OrderStatus.delivery_failed):
            raise HTTPException(status_code=409, detail="Delivery can start only after parcel pickup")
        ok, err = await transition_order_status(db, order, "out_for_delivery", changed_by=partner.id,
            note=data.note or "Delivery started", expected_version=order.version,
            actor_type="delivery_partner")
        if not ok:
            raise HTTPException(status_code=409, detail=err)
        assignment.started_at = now
    elif action == "failed":
        if order.status != OrderStatus.out_for_delivery.value:
            raise HTTPException(status_code=409, detail="A delivery attempt must be in progress before reporting failure")
        ok, err = await transition_order_status(db, order, "delivery_failed", changed_by=partner.id,
            note=data.note, expected_version=order.version, actor_type="delivery_partner")
        if not ok:
            raise HTTPException(status_code=409, detail=err)
        assignment.failure_reason = data.note
    elif action == "accept":
        assignment.accepted_at = now
    assignment.status = target
    assignment.version += 1
    assignment.updated_at = now
    db.add(DeliveryAssignmentHistory(assignment_id=assignment.id, order_id=order.id, actor_id=partner.id,
        from_status=expected, to_status=target, note=data.note))
    await db.flush()
    assignment.order_number = order.order_number
    assignment.fulfillment_status = order.status.value
    return assignment


def action_endpoint(action: str):
    async def endpoint(order_id: uuid.UUID, data: DeliveryActionIn, db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
        return await update_assignment(order_id, data, partner, db, action)
    return endpoint


for action in ("accept", "reject", "pickup", "start", "failed"):
    router.add_api_route(f"/orders/{{order_id}}/{action}", action_endpoint(action), methods=["POST"],
        response_model=DeliveryAssignmentOut, name=f"delivery_{action}")
