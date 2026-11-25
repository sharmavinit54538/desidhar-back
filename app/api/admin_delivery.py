import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.passwords import hash_password
from app.models.user import User, Role
from app.models.order import Order, OrderStatus
from app.models.delivery_management import DeliveryPartnerProfile, DeliveryAssignment, DeliveryAssignmentHistory
from app.schemas.delivery_management import DeliveryPartnerCreateIn, DeliveryPartnerOut, DeliveryAssignmentIn, DeliveryAssignmentOut, EligibleDeliveryPartnerOut
from app.models.delivery_finance import CashSettlement, CashSettlementItem
from app.models.order_lifecycle import OrderNotification
from app.schemas.delivery_finance import CashSettlementOut, CashSettlementReconcileIn, CashSettlementRejectIn

router = APIRouter(prefix="/admin/delivery", tags=["admin-delivery"])

ACTIVE_ASSIGNMENTS = ("assigned", "accepted", "picked_up", "in_progress")


@router.get("/partners", response_model=list[DeliveryPartnerOut])
async def list_partners(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    rows = (await db.execute(
        select(User, DeliveryPartnerProfile)
        .join(DeliveryPartnerProfile, DeliveryPartnerProfile.user_id == User.id)
        .where(User.role == Role.delivery_partner)
        .order_by(User.full_name, User.username)
    )).all()
    result = []
    for user, profile in rows:
        active = await db.scalar(select(func.count()).select_from(DeliveryAssignment).where(
            DeliveryAssignment.partner_id == user.id, DeliveryAssignment.status.in_(ACTIVE_ASSIGNMENTS))) or 0
        completed = await db.scalar(select(func.count()).select_from(DeliveryAssignment).where(
            DeliveryAssignment.partner_id == user.id, DeliveryAssignment.status == "completed")) or 0
        result.append(DeliveryPartnerOut(
            user_id=user.id, employee_id=profile.employee_id, full_name=user.full_name, phone=user.phone,
            email=user.email, is_active=user.is_active, service_area=profile.service_area,
            service_pincodes=profile.service_pincodes, vehicle_type=profile.vehicle_type,
            vehicle_registration=profile.vehicle_registration, max_active_deliveries=profile.max_active_deliveries,
            availability=profile.availability, active_assignments=active, completed_deliveries=completed))
    return result


@router.get("/orders/{order_id}/eligible-partners", response_model=list[EligibleDeliveryPartnerOut])
async def get_eligible_partners(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    rows = (await db.execute(
        select(User, DeliveryPartnerProfile)
        .join(DeliveryPartnerProfile, DeliveryPartnerProfile.user_id == User.id)
        .where(User.role == Role.delivery_partner)
        .order_by(User.full_name, User.username)
    )).all()

    result = []
    for user, profile in rows:
        active = await db.scalar(select(func.count()).select_from(DeliveryAssignment).where(
            DeliveryAssignment.partner_id == user.id, DeliveryAssignment.status.in_(ACTIVE_ASSIGNMENTS))) or 0
        completed = await db.scalar(select(func.count()).select_from(DeliveryAssignment).where(
            DeliveryAssignment.partner_id == user.id, DeliveryAssignment.status == "completed")) or 0

        remaining_capacity = max(0, profile.max_active_deliveries - active)

        is_eligible = True
        reasons = []

        if not user.is_active:
            is_eligible = False
            reasons.append("Partner account is inactive")
        if profile.availability != "available":
            is_eligible = False
            reasons.append("Partner is not available")
        if active >= profile.max_active_deliveries:
            is_eligible = False
            reasons.append("Partner has reached maximum active delivery capacity")
        if order.shipping_pincode not in profile.service_pincodes:
            is_eligible = False
            reasons.append("Order PIN code is outside partner's service area")

        result.append(EligibleDeliveryPartnerOut(
            user_id=user.id, employee_id=profile.employee_id, full_name=user.full_name, phone=user.phone,
            email=user.email, is_active=user.is_active, service_area=profile.service_area,
            service_pincodes=profile.service_pincodes, vehicle_type=profile.vehicle_type,
            vehicle_registration=profile.vehicle_registration, max_active_deliveries=profile.max_active_deliveries,
            availability=profile.availability, active_assignments=active, completed_deliveries=completed,
            remaining_capacity=remaining_capacity, is_eligible=is_eligible,
            ineligibility_reason="; ".join(reasons) if reasons else None))

    return result


@router.post("/partners", response_model=DeliveryPartnerOut, status_code=status.HTTP_201_CREATED)
async def create_partner(data: DeliveryPartnerCreateIn, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    username = data.username.strip().lower()
    employee = data.employee_id.strip()
    existing = await db.scalar(select(User.id).where(User.username == username))
    if existing or await db.scalar(select(DeliveryPartnerProfile.user_id).where(DeliveryPartnerProfile.employee_id == employee)):
        raise HTTPException(status_code=409, detail="Username or delivery partner ID is already in use")
    pins = list(dict.fromkeys(data.service_pincodes))
    if any(len(pin) != 6 or not pin.isdigit() or pin.startswith("0") for pin in pins):
        raise HTTPException(status_code=422, detail="Service PIN codes must be valid six digit PIN codes")
    user = User(role=Role.delivery_partner, username=username, password_hash=hash_password(data.password),
                email=data.email.strip().lower() if data.email else None, full_name=data.full_name.strip(),
                phone=data.phone, is_active=True)
    db.add(user)
    await db.flush()
    profile = DeliveryPartnerProfile(
        user_id=user.id, employee_id=employee, service_area=data.service_area,
        service_pincodes=pins, vehicle_type=data.vehicle_type, vehicle_registration=data.vehicle_registration,
        max_active_deliveries=data.max_active_deliveries, availability="offline")
    db.add(profile)
    await db.flush()
    return DeliveryPartnerOut(user_id=user.id, employee_id=employee, full_name=user.full_name, phone=user.phone,
        email=user.email, is_active=user.is_active, service_area=profile.service_area,
        service_pincodes=profile.service_pincodes, vehicle_type=profile.vehicle_type,
        vehicle_registration=profile.vehicle_registration, max_active_deliveries=profile.max_active_deliveries,
        availability=profile.availability)


@router.patch("/partners/{partner_id}/active", response_model=DeliveryPartnerOut)
async def set_partner_active(partner_id: uuid.UUID, active: bool, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    user = (await db.execute(select(User).where(User.id == partner_id, User.role == Role.delivery_partner).with_for_update())).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Delivery partner not found")
    profile = await db.get(DeliveryPartnerProfile, partner_id)
    user.is_active = active
    if not active:
        profile.availability = "offline"
    else:
        profile.availability = "available"
    await db.flush()
    return DeliveryPartnerOut(user_id=user.id, employee_id=profile.employee_id, full_name=user.full_name,
        phone=user.phone, email=user.email, is_active=user.is_active, service_area=profile.service_area,
        service_pincodes=profile.service_pincodes, vehicle_type=profile.vehicle_type,
        vehicle_registration=profile.vehicle_registration, max_active_deliveries=profile.max_active_deliveries,
        availability=profile.availability)


async def assign(order_id: uuid.UUID, data: DeliveryAssignmentIn, admin: User, db: AsyncSession, reassign: bool):
    order = (await db.execute(select(Order).where(Order.id == order_id).with_for_update())).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in (OrderStatus.packed, OrderStatus.delivery_failed):
        raise HTTPException(status_code=409, detail="Delivery can only be assigned to packed or rescheduled failed deliveries")
    current = (await db.execute(select(DeliveryAssignment).where(
        DeliveryAssignment.order_id == order.id, DeliveryAssignment.status.in_(ACTIVE_ASSIGNMENTS)).with_for_update())).scalar_one_or_none()
    if current and not reassign:
        raise HTTPException(status_code=409, detail="Order already has an active delivery assignment; use reassign")
    if current and reassign:
        old = current.status
        current.status = "cancelled"
        current.version += 1
        current.updated_at = func.now()
        db.add(DeliveryAssignmentHistory(assignment_id=current.id, order_id=order.id, actor_id=admin.id,
            from_status=old, to_status="cancelled", note="Reassigned by administrator"))
        db.add(OrderNotification(order_id=order.id, user_id=current.partner_id, event_type="delivery_assignment",
            event_key=f"assignment:{current.id}:cancelled:{current.version}", channel="in_app", recipient=None,
            message=f"Delivery assignment for order {order.order_number} was cancelled",
            payload={"assignment_id": str(current.id), "order_id": str(order.id), "status": "cancelled"}, status="queued"))
    elif reassign:
        raise HTTPException(status_code=409, detail="No active assignment to reassign")
    partner = (await db.execute(select(User).where(User.id == data.partner_id, User.role == Role.delivery_partner).with_for_update())).scalar_one_or_none()
    if not partner or not partner.is_active:
        raise HTTPException(status_code=422, detail="Choose an active delivery partner")
    profile = await db.get(DeliveryPartnerProfile, partner.id)
    active_count = await db.scalar(select(func.count()).select_from(DeliveryAssignment).where(
        DeliveryAssignment.partner_id == partner.id, DeliveryAssignment.status.in_(ACTIVE_ASSIGNMENTS))) or 0
    if profile.availability != "available":
        raise HTTPException(status_code=409, detail="Delivery partner is not marked available")
    if active_count >= profile.max_active_deliveries:
        raise HTTPException(status_code=409, detail="Delivery partner has reached active delivery capacity")
    if order.shipping_pincode not in profile.service_pincodes:
        raise HTTPException(status_code=422, detail="Order PIN code is outside the partner's configured service area")
    assignment = DeliveryAssignment(order_id=order.id, partner_id=partner.id, assigned_by=admin.id, status="assigned")
    db.add(assignment)
    await db.flush()
    db.add(DeliveryAssignmentHistory(assignment_id=assignment.id, order_id=order.id, actor_id=admin.id,
        from_status=None, to_status="assigned", note="Assigned by administrator"))
    db.add(OrderNotification(order_id=order.id, user_id=partner.id, event_type="delivery_assignment",
        event_key=f"assignment:{assignment.id}:assigned", channel="in_app", recipient=None,
        message=f"New delivery assignment for order {order.order_number}",
        payload={"assignment_id": str(assignment.id), "order_id": str(order.id), "status": "assigned"}, status="queued"))
    await db.flush()
    assignment.order_number = order.order_number
    assignment.fulfillment_status = order.status.value
    return assignment


@router.post("/orders/{order_id}/assign", response_model=DeliveryAssignmentOut, status_code=201)
async def assign_delivery(order_id: uuid.UUID, data: DeliveryAssignmentIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    return await assign(order_id, data, admin, db, False)


@router.post("/orders/{order_id}/reassign", response_model=DeliveryAssignmentOut)
async def reassign_delivery(order_id: uuid.UUID, data: DeliveryAssignmentIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    return await assign(order_id, data, admin, db, True)


@router.get("/orders/{order_id}/assignments", response_model=list[DeliveryAssignmentOut])
async def assignment_history(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    rows = list((await db.execute(select(DeliveryAssignment).where(DeliveryAssignment.order_id == order_id).order_by(DeliveryAssignment.assigned_at.desc()))).scalars().all())
    order = await db.get(Order, order_id)
    for row in rows:
        row.order_number = order.order_number if order else None
        row.fulfillment_status = order.status.value if order else None
    return rows


@router.get("/settlements", response_model=list[CashSettlementOut])
async def list_settlements(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    return list((await db.execute(select(CashSettlement).order_by(CashSettlement.submitted_at.desc()).limit(200))).scalars().all())


@router.post("/settlements/{settlement_id}/reconcile", response_model=CashSettlementOut)
async def reconcile_settlement(settlement_id: uuid.UUID, data: CashSettlementReconcileIn,
    db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    settlement = (await db.execute(select(CashSettlement).where(CashSettlement.id == settlement_id).with_for_update())).scalar_one_or_none()
    if not settlement:
        raise HTTPException(status_code=404, detail="Cash settlement not found")
    if settlement.status not in ("submitted", "discrepancy"):
        raise HTTPException(status_code=409, detail=f"Settlement is already {settlement.status}")
    settlement.verified_amount_paise = data.verified_amount_paise
    settlement.deposit_reference = data.deposit_reference
    settlement.review_note = data.note
    settlement.reviewed_by = admin.id
    settlement.reviewed_at = datetime.now(timezone.utc)
    settlement.status = "approved" if data.verified_amount_paise == settlement.expected_amount_paise else "discrepancy"
    await db.flush()
    return settlement


@router.post("/settlements/{settlement_id}/approve", response_model=CashSettlementOut)
async def approve_settlement(settlement_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    settlement = (await db.execute(select(CashSettlement).where(CashSettlement.id == settlement_id).with_for_update())).scalar_one_or_none()
    if not settlement:
        raise HTTPException(status_code=404, detail="Cash settlement not found")
    if settlement.status != "approved" or settlement.verified_amount_paise != settlement.expected_amount_paise:
        raise HTTPException(status_code=409, detail="Record and verify the full deposited amount before approval")
    settlement.reviewed_by = admin.id
    await db.flush()
    return settlement


@router.post("/settlements/{settlement_id}/reject", response_model=CashSettlementOut)
async def reject_settlement(settlement_id: uuid.UUID, data: CashSettlementRejectIn,
    db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    settlement = (await db.execute(select(CashSettlement).where(CashSettlement.id == settlement_id).with_for_update())).scalar_one_or_none()
    if not settlement:
        raise HTTPException(status_code=404, detail="Cash settlement not found")
    if settlement.status not in ("submitted", "discrepancy"):
        raise HTTPException(status_code=409, detail=f"Settlement is already {settlement.status}")
    settlement.status = "rejected"
    settlement.review_note = data.note
    settlement.reviewed_by = admin.id
    settlement.reviewed_at = datetime.now(timezone.utc)
    # Rejected cash remains unsettled and may be included in a later submission.
    from sqlalchemy import delete
    await db.execute(delete(CashSettlementItem).where(CashSettlementItem.settlement_id == settlement.id))
    await db.flush()
    return settlement
