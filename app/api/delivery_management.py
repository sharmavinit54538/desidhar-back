import uuid
import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func, exists, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_delivery_partner
from app.core.rate_limit import limiter
from app.core.tokens import create_access_token, create_refresh_token
from app.models.user import User
from app.models.order import Order, OrderStatus
from app.models.delivery_management import DeliveryPartnerProfile, DeliveryAssignment, DeliveryAssignmentHistory
from app.models.delivery_finance import CODCollection, CashSettlement, CashSettlementItem, DeliveryOTP
from app.models.payment import Payment
from app.models.order import PaymentMethod, PaymentStatus
from app.models.order_lifecycle import OrderNotification
from app.core.config import get_settings
from app.schemas.delivery_finance import DeliveryCashCollectionIn, DeliveryOTPVerifyIn, CashSettlementCreateIn, CashSettlementOut
from app.schemas.auth import AdminLogin, TokenResponse
from app.schemas.delivery_management import DeliveryActionIn, DeliveryAssignmentOut, DeliveryOrderOut
from app.services.auth_service import authenticate_delivery_partner
from app.services.order_service import transition_order_status
from app.services.email_service import send_delivery_otp_email

auth_router = APIRouter(prefix="/delivery/auth", tags=["delivery-auth"])
router = APIRouter(prefix="/delivery", tags=["delivery-partner"])
ACTIVE = ("assigned", "accepted", "picked_up", "in_progress")
settings = get_settings()


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
        "is_suspended": profile.is_suspended, "service_area": profile.service_area,
        "service_pincodes": profile.service_pincodes, "max_active_deliveries": profile.max_active_deliveries}


@router.patch("/availability")
async def set_availability(availability: str, db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    if availability not in ("available", "offline"):
        raise HTTPException(status_code=422, detail="Availability must be available or offline")
    locked_user = (await db.execute(select(User).where(User.id == partner.id).with_for_update())).scalar_one()
    profile = (await db.execute(
        select(DeliveryPartnerProfile).where(DeliveryPartnerProfile.user_id == partner.id).with_for_update()
    )).scalar_one_or_none()
    if not profile or profile.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Delivery partner profile not found")
    if availability == "available" and (not locked_user.is_active or profile.is_suspended):
        raise HTTPException(status_code=409, detail="Suspended or inactive partners cannot go available")
    profile.availability = availability
    profile.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {"availability": profile.availability}


@router.get("/notifications")
async def list_partner_notifications(db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    rows = list((await db.execute(
        select(OrderNotification)
        .where(OrderNotification.user_id == partner.id, OrderNotification.channel == "in_app")
        .order_by(OrderNotification.created_at.desc())
        .limit(50)
    )).scalars().all())
    return [
        {
            "id": str(row.id),
            "order_id": str(row.order_id),
            "event_type": row.event_type,
            "message": row.message,
            "payload": row.payload,
            "status": row.status,
            "created_at": row.created_at,
        }
        for row in rows
    ]


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
                "version": order.version, "created_at": order.created_at, "items": order.items, "assignment": assignment})
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
        "outstanding_amount_paise": order.outstanding_paise, "version": order.version, "created_at": order.created_at,
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
    if action == "failed" and not data.note:
        raise HTTPException(status_code=422, detail="Provide a delivery failure reason")
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
        if order.status != OrderStatus.out_for_delivery:
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
    db.add(OrderNotification(order_id=order.id, user_id=assignment.assigned_by, event_type="delivery_progress",
        event_key=f"delivery:{assignment.id}:{assignment.version}:{target}", channel="in_app", recipient=None,
        message=f"Delivery partner reported {target.replace('_', ' ')} for order {order.order_number}",
        payload={"assignment_id": str(assignment.id), "order_id": str(order.id), "status": target}, status="queued"))
    await db.flush()
    await db.refresh(assignment)
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


def _delivery_otp_hash(code: str, order_id: uuid.UUID) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"delivery:{order_id}:{code}".encode(), hashlib.sha256).hexdigest()


@router.post("/orders/{order_id}/collect-payment")
async def collect_cod_cash(order_id: uuid.UUID, data: DeliveryCashCollectionIn,
    db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    replay = await db.scalar(select(CODCollection).where(CODCollection.partner_id == partner.id,
        CODCollection.idempotency_key == data.idempotency_key))
    if replay:
        if replay.order_id != order_id or replay.amount_paise != data.amount_paise:
            raise HTTPException(status_code=409, detail="Idempotency key was already used for a different collection")
        return {"id": str(replay.id), "order_id": str(order_id), "amount_paise": replay.amount_paise,
            "method": replay.method, "payment_status": "paid"}
    order, assignment = await delivery_order(db, order_id, partner, lock=True)
    existing = await db.scalar(select(CODCollection).where(CODCollection.partner_id == partner.id,
        CODCollection.idempotency_key == data.idempotency_key))
    if existing:
        if existing.order_id != order.id or existing.amount_paise != data.amount_paise:
            raise HTTPException(status_code=409, detail="Idempotency key was already used for a different collection")
        return {"id": str(existing.id), "order_id": str(order.id), "amount_paise": existing.amount_paise,
            "method": existing.method, "payment_status": order.payment_status.value}
    if data.expected_order_version != order.version or data.expected_assignment_version != assignment.version:
        raise HTTPException(status_code=409, detail="Order or assignment changed; refresh before collecting COD")
    if assignment.status != "in_progress" or order.status != OrderStatus.out_for_delivery:
        raise HTTPException(status_code=409, detail="COD can only be collected during an active out-for-delivery attempt")
    if order.payment_method != PaymentMethod.cod or order.payment_status == PaymentStatus.paid:
        raise HTTPException(status_code=409, detail="This order has no outstanding COD payment")
    outstanding = order.outstanding_paise
    if data.amount_paise != outstanding:
        raise HTTPException(status_code=422, detail=f"Collect the exact outstanding amount of {outstanding} paise")
    now = datetime.now(timezone.utc)
    payment = next((p for p in order.payments if p.method == PaymentMethod.cod and p.paid_at is None), None)
    if payment is None:
        raise HTTPException(status_code=409, detail="No pending COD payment record exists for this order")
    payment.status = PaymentStatus.paid
    payment.paid_at = now
    payment.collected_by = partner.id
    payment.collection_method = "cash"
    payment.collection_reference = data.idempotency_key
    payment.idempotency_key = data.idempotency_key
    order.payment_status = PaymentStatus.paid
    order.version += 1
    order.updated_at = now
    assignment.version += 1
    assignment.updated_at = now
    collection = CODCollection(order_id=order.id, payment_id=payment.id, partner_id=partner.id,
        amount_paise=data.amount_paise, method="cash", idempotency_key=data.idempotency_key,
        collected_at=now)
    db.add(collection)
    await db.flush()
    db.add(OrderNotification(order_id=order.id, user_id=order.user_id, event_type="payment_confirmed",
        event_key=f"delivery-payment:{collection.id}:customer", channel="in_app", recipient=None,
        message=f"Cash payment received for order {order.order_number}",
        payload={"order_id": str(order.id), "amount_paise": collection.amount_paise, "method": "cash"}, status="queued"))
    db.add(OrderNotification(order_id=order.id, user_id=assignment.assigned_by, event_type="cod_collected",
        event_key=f"delivery-payment:{collection.id}:admin", channel="in_app", recipient=None,
        message=f"COD cash collected for order {order.order_number}",
        payload={"order_id": str(order.id), "partner_id": str(partner.id), "amount_paise": collection.amount_paise}, status="queued"))
    return {"id": str(collection.id), "order_id": str(order.id), "amount_paise": collection.amount_paise,
        "method": collection.method, "payment_status": order.payment_status.value,
        "assignment_version": assignment.version, "order_version": order.version}


@router.post("/orders/{order_id}/request-otp", status_code=202)
@limiter.limit("5/hour")
async def request_delivery_otp(request: Request, order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    order, assignment = await delivery_order(db, order_id, partner, lock=True)
    if assignment.status != "in_progress" or order.status != OrderStatus.out_for_delivery:
        raise HTTPException(status_code=409, detail="Delivery OTP is available only during an active delivery attempt")
    if order.payment_method == PaymentMethod.cod and order.payment_status != PaymentStatus.paid:
        raise HTTPException(status_code=409, detail="Collect and verify the exact COD cash amount before requesting delivery confirmation")
    customer = await db.get(User, order.user_id)
    if not customer or not customer.email:
        raise HTTPException(status_code=422, detail="The customer does not have an email address for delivery verification")
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = datetime.now(timezone.utc)
    otp_row = DeliveryOTP(order_id=order.id, assignment_id=assignment.id,
        code_hash=_delivery_otp_hash(code, order.id), expires_at=now + timedelta(minutes=10))
    db.add(otp_row)
    try:
        await send_delivery_otp_email(customer.email, code, order.order_number)
    except Exception:
        raise HTTPException(status_code=503, detail="Delivery verification email could not be sent; try again later")
    await db.flush()
    return {"message": "Delivery verification code sent to the customer's registered email", "expires_at": otp_row.expires_at}


@router.post("/orders/{order_id}/verify-otp")
async def verify_delivery_otp(order_id: uuid.UUID, data: DeliveryOTPVerifyIn,
    db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    order, assignment = await delivery_order(db, order_id, partner, lock=True)
    otp_row = (await db.execute(select(DeliveryOTP).where(DeliveryOTP.order_id == order.id,
        DeliveryOTP.assignment_id == assignment.id, DeliveryOTP.used_at.is_(None))
        .order_by(DeliveryOTP.created_at.desc()).limit(1).with_for_update())).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not otp_row or otp_row.expires_at <= now or otp_row.attempts >= 5:
        raise HTTPException(status_code=401, detail="Delivery verification code is invalid or expired")
    if not hmac.compare_digest(otp_row.code_hash, _delivery_otp_hash(data.otp, order.id)):
        otp_row.attempts += 1
        await db.flush()
        # Persist a failed-attempt counter even though the API returns 401.
        await db.commit()
        raise HTTPException(status_code=401, detail="Delivery verification code is invalid or expired")
    if order.status != OrderStatus.out_for_delivery or assignment.status != "in_progress":
        raise HTTPException(status_code=409, detail="Order or assignment is no longer in a deliverable state")
    if order.payment_status != PaymentStatus.paid:
        raise HTTPException(status_code=409, detail="Payment must be verified before delivery can be completed")
    ok, err = await transition_order_status(db, order, OrderStatus.delivered.value,
        changed_by=partner.id, note="Customer delivery OTP verified", expected_version=order.version,
        actor_type="delivery_partner")
    if not ok:
        raise HTTPException(status_code=409, detail=err)
    otp_row.used_at = now
    assignment.status = "completed"
    assignment.completed_at = now
    assignment.version += 1
    assignment.updated_at = now
    db.add(DeliveryAssignmentHistory(assignment_id=assignment.id, order_id=order.id, actor_id=partner.id,
        from_status="in_progress", to_status="completed", note="Customer delivery OTP verified"))
    await db.flush()
    return {"order_id": str(order.id), "order_status": order.status.value,
        "payment_status": order.payment_status.value, "assignment_status": assignment.status}


@router.get("/cash/summary")
async def partner_cash_summary(db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    collected = await db.scalar(select(func.coalesce(func.sum(CODCollection.amount_paise), 0)).where(CODCollection.partner_id == partner.id)) or 0
    settled = await db.scalar(select(func.coalesce(func.sum(CashSettlement.expected_amount_paise), 0)).where(
        CashSettlement.partner_id == partner.id, CashSettlement.status == "approved")) or 0
    available = await db.scalar(select(func.coalesce(func.sum(CODCollection.amount_paise), 0)).where(
        CODCollection.partner_id == partner.id,
        ~exists(select(CashSettlementItem.id).where(CashSettlementItem.collection_id == CODCollection.id)))) or 0
    return {"collected_paise": collected, "deposited_paise": settled,
        "pending_paise": max(0, collected - settled), "available_to_submit_paise": available}


@router.get("/cash/collections")
async def partner_cash_collections(db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    rows = list((await db.execute(select(CODCollection).where(CODCollection.partner_id == partner.id)
        .order_by(CODCollection.collected_at.desc()).limit(100))).scalars().all())
    return [{"id": str(row.id), "order_id": str(row.order_id), "amount_paise": row.amount_paise,
        "method": row.method, "collected_at": row.collected_at} for row in rows]


@router.get("/cash/settlements", response_model=list[CashSettlementOut])
async def partner_cash_settlements(db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    return list((await db.execute(select(CashSettlement).where(CashSettlement.partner_id == partner.id)
        .order_by(CashSettlement.submitted_at.desc()).limit(100))).scalars().all())


@router.post("/cash/settlements", response_model=CashSettlementOut, status_code=201)
async def submit_cash_settlement(data: CashSettlementCreateIn, db: AsyncSession = Depends(get_db), partner: User = Depends(require_delivery_partner)):
    await db.execute(select(User.id).where(User.id == partner.id).with_for_update())
    unallocated = list((await db.execute(select(CODCollection).where(CODCollection.partner_id == partner.id,
        ~exists(select(CashSettlementItem.id).where(CashSettlementItem.collection_id == CODCollection.id)))
        .order_by(CODCollection.collected_at).with_for_update())).scalars().all())
    if not unallocated:
        raise HTTPException(status_code=409, detail="There are no unsubmitted cash collections")
    amount = sum(row.amount_paise for row in unallocated)
    settlement = CashSettlement(partner_id=partner.id, expected_amount_paise=amount, status="submitted", submission_note=data.note)
    db.add(settlement)
    await db.flush()
    db.add_all([CashSettlementItem(settlement_id=settlement.id, collection_id=row.id) for row in unallocated])
    await db.flush()
    return settlement
