import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.core.config import get_settings
from app.core.passwords import hash_password
from app.models.delivery_finance import CashSettlement, CashSettlementItem
from app.models.delivery_management import (
    DeliveryAssignment,
    DeliveryAssignmentHistory,
    DeliveryPartnerProfile,
)
from app.models.order import Order, OrderStatus
from app.models.order_lifecycle import OrderAuditLog, OrderNotification
from app.models.user import Role, User
from app.schemas.delivery_finance import (
    CashSettlementOut,
    CashSettlementReconcileIn,
    CashSettlementRejectIn,
)
from app.schemas.delivery_management import (
    DeliveryAssignmentHistoryOut,
    DeliveryAssignmentIn,
    DeliveryAssignmentOut,
    DeliveryPartnerCreateIn,
    DeliveryPartnerDetailOut,
    DeliveryPartnerOut,
    DeliveryPartnerUpdateIn,
    EligibleDeliveryPartnerOut,
)
from app.services.email_service import dispatch_order_notification

router = APIRouter(prefix="/admin/delivery", tags=["admin-delivery"])

ACTIVE_ASSIGNMENTS = ("assigned", "accepted", "picked_up", "in_progress")
ASSIGNABLE_ORDER_STATUSES = (OrderStatus.packed, OrderStatus.delivery_failed)
TERMINAL_ORDER_STATUSES = (
    OrderStatus.cancelled,
    OrderStatus.returned,
    OrderStatus.delivered,
    OrderStatus.return_requested,
    OrderStatus.return_approved,
    OrderStatus.return_rejected,
    OrderStatus.return_in_transit,
)


def _normalize_pincode(pin: str | None) -> str:
    return (pin or "").strip()


def _normalize_pincodes(raw_pins: list | None) -> list[str]:
    return list(dict.fromkeys(str(pin).strip() for pin in (raw_pins or []) if str(pin).strip()))


def _validate_pincodes(pins: list[str]) -> None:
    if any(len(pin) != 6 or not pin.isdigit() or pin.startswith("0") for pin in pins):
        raise HTTPException(status_code=422, detail="Service PIN codes must be valid 6-digit PIN codes")


async def _partner_counts_map(
    db: AsyncSession, partner_ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    if not partner_ids:
        return {}, {}
    active_rows = (
        await db.execute(
            select(DeliveryAssignment.partner_id, func.count())
            .where(
                DeliveryAssignment.partner_id.in_(partner_ids),
                DeliveryAssignment.status.in_(ACTIVE_ASSIGNMENTS),
            )
            .group_by(DeliveryAssignment.partner_id)
        )
    ).all()
    completed_rows = (
        await db.execute(
            select(DeliveryAssignment.partner_id, func.count())
            .where(
                DeliveryAssignment.partner_id.in_(partner_ids),
                DeliveryAssignment.status == "completed",
            )
            .group_by(DeliveryAssignment.partner_id)
        )
    ).all()
    return dict(active_rows), dict(completed_rows)


async def _single_partner_counts(db: AsyncSession, partner_id: uuid.UUID) -> tuple[int, int]:
    active = (
        await db.scalar(
            select(func.count())
            .select_from(DeliveryAssignment)
            .where(
                DeliveryAssignment.partner_id == partner_id,
                DeliveryAssignment.status.in_(ACTIVE_ASSIGNMENTS),
            )
        )
    ) or 0
    completed = (
        await db.scalar(
            select(func.count())
            .select_from(DeliveryAssignment)
            .where(
                DeliveryAssignment.partner_id == partner_id,
                DeliveryAssignment.status == "completed",
            )
        )
    ) or 0
    return active, completed


def _evaluate_partner_eligibility(
    user: User,
    profile: DeliveryPartnerProfile,
    order_pincode: str,
    active_count: int,
    now: datetime,
) -> tuple[bool, list[str], int]:
    remaining_capacity = max(0, profile.max_active_deliveries - active_count)
    reasons: list[str] = []

    if profile.deleted_at is not None:
        reasons.append("Partner account has been deleted")
    if not user.is_active:
        reasons.append("Partner account is inactive")
    if profile.is_suspended or (user.locked_until is not None and user.locked_until > now):
        reasons.append("Partner account is suspended")
    if (profile.availability or "").strip().lower() != "available":
        reasons.append("Partner is not available")
    if active_count >= profile.max_active_deliveries:
        reasons.append("Partner has reached maximum active delivery capacity")

    normalized_pins = set(_normalize_pincodes(profile.service_pincodes))
    if not order_pincode or order_pincode not in normalized_pins:
        reasons.append("Order PIN code is outside partner's service area")

    return len(reasons) == 0, reasons, remaining_capacity


def _build_partner_out(
    user: User,
    profile: DeliveryPartnerProfile,
    active_count: int = 0,
    completed_count: int = 0,
) -> DeliveryPartnerOut:
    pins = _normalize_pincodes(profile.service_pincodes)
    return DeliveryPartnerOut(
        user_id=user.id,
        employee_id=profile.employee_id,
        full_name=user.full_name,
        phone=user.phone,
        email=user.email,
        is_active=user.is_active,
        is_suspended=profile.is_suspended,
        deleted_at=profile.deleted_at,
        service_area=profile.service_area,
        service_pincodes=pins,
        vehicle_type=profile.vehicle_type,
        vehicle_registration=profile.vehicle_registration,
        max_active_deliveries=profile.max_active_deliveries,
        availability=profile.availability,
        active_assignments=active_count,
        completed_deliveries=completed_count,
        remaining_capacity=max(0, profile.max_active_deliveries - active_count),
    )


def _build_history_out(entry: DeliveryAssignmentHistory) -> DeliveryAssignmentHistoryOut:
    return DeliveryAssignmentHistoryOut(
        id=entry.id,
        assignment_id=entry.assignment_id,
        order_id=entry.order_id,
        actor_id=entry.actor_id,
        actor_name=entry.actor_name,
        from_status=entry.from_status,
        to_status=entry.to_status,
        note=entry.note,
        created_at=entry.created_at,
    )


def _build_assignment_out(
    assignment: DeliveryAssignment,
    order: Order | None = None,
    partner: User | None = None,
    profile: DeliveryPartnerProfile | None = None,
    assigned_by_user: User | None = None,
    history_entries: list[DeliveryAssignmentHistory] | None = None,
) -> DeliveryAssignmentOut:
    p_user = partner or assignment.partner
    p_profile = profile or assignment.partner_profile
    ab_user = assigned_by_user or assignment.assigned_by_user
    hist = history_entries if history_entries is not None else list(assignment.history or [])
    expected_date = None
    if order is not None:
        expected_date = order.revised_delivery_date or order.estimated_delivery_date

    return DeliveryAssignmentOut(
        id=assignment.id,
        order_id=assignment.order_id,
        partner_id=assignment.partner_id,
        status=assignment.status,
        version=assignment.version,
        assigned_at=assignment.assigned_at,
        accepted_at=assignment.accepted_at,
        picked_up_at=assignment.picked_up_at,
        started_at=assignment.started_at,
        completed_at=assignment.completed_at,
        failure_reason=assignment.failure_reason,
        order_number=order.order_number if order else None,
        fulfillment_status=order.status.value if order else None,
        delivery_status=order.delivery_status if order else None,
        partner_name=p_user.full_name if p_user else None,
        partner_phone=p_user.phone if p_user else None,
        partner_employee_id=p_profile.employee_id if p_profile else None,
        partner_service_area=p_profile.service_area if p_profile else None,
        partner_availability=p_profile.availability if p_profile else None,
        assigned_by_name=(ab_user.full_name or ab_user.username) if ab_user else None,
        expected_delivery_date=expected_date,
        estimated_delivery_end_date=order.estimated_delivery_end_date if order else None,
        shipping_pincode=order.shipping_pincode if order else None,
        shipping_name=order.shipping_name if order else None,
        history=[_build_history_out(entry) for entry in hist],
    )


async def _lock_partner_and_profile(
    db: AsyncSession, partner_id: uuid.UUID, *, allow_deleted: bool = False
) -> tuple[User, DeliveryPartnerProfile]:
    user = (
        await db.execute(
            select(User)
            .where(User.id == partner_id, User.role == Role.delivery_partner)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Delivery partner not found")

    profile = (
        await db.execute(
            select(DeliveryPartnerProfile)
            .where(DeliveryPartnerProfile.user_id == partner_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not profile or (not allow_deleted and profile.deleted_at is not None):
        raise HTTPException(status_code=404, detail="Delivery partner not found")

    return user, profile


@router.get("/partners", response_model=list[DeliveryPartnerOut])
async def list_partners(
    include_deleted: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    stmt = (
        select(User, DeliveryPartnerProfile)
        .join(DeliveryPartnerProfile, DeliveryPartnerProfile.user_id == User.id)
        .where(User.role == Role.delivery_partner)
    )
    if not include_deleted:
        stmt = stmt.where(DeliveryPartnerProfile.deleted_at.is_(None))
    rows = (await db.execute(stmt.order_by(User.full_name, User.username))).all()
    partner_ids = [user.id for user, _ in rows]
    active_map, completed_map = await _partner_counts_map(db, partner_ids)
    return [
        _build_partner_out(user, profile, active_map.get(user.id, 0), completed_map.get(user.id, 0))
        for user, profile in rows
    ]


@router.get("/partners/{partner_id}", response_model=DeliveryPartnerDetailOut)
async def get_partner_detail(
    partner_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    row = (
        await db.execute(
            select(User, DeliveryPartnerProfile)
            .join(DeliveryPartnerProfile, DeliveryPartnerProfile.user_id == User.id)
            .where(User.id == partner_id, User.role == Role.delivery_partner)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Delivery partner not found")
    user, profile = row
    active_count, completed_count = await _single_partner_counts(db, user.id)

    active_rows = list(
        (
            await db.execute(
                select(DeliveryAssignment)
                .where(
                    DeliveryAssignment.partner_id == user.id,
                    DeliveryAssignment.status.in_(ACTIVE_ASSIGNMENTS),
                )
                .order_by(DeliveryAssignment.assigned_at.desc())
            )
        ).scalars().all()
    )
    completed_rows = list(
        (
            await db.execute(
                select(DeliveryAssignment)
                .where(
                    DeliveryAssignment.partner_id == user.id,
                    DeliveryAssignment.status == "completed",
                )
                .order_by(DeliveryAssignment.completed_at.desc(), DeliveryAssignment.assigned_at.desc())
                .limit(50)
            )
        ).scalars().all()
    )
    order_ids = list({a.order_id for a in (*active_rows, *completed_rows)})
    order_map = (
        {
            o.id: o
            for o in (await db.execute(select(Order).where(Order.id.in_(order_ids)))).scalars().all()
        }
        if order_ids
        else {}
    )
    hist_rows = list(
        (
            await db.execute(
                select(DeliveryAssignmentHistory)
                .join(DeliveryAssignment, DeliveryAssignment.id == DeliveryAssignmentHistory.assignment_id)
                .where(DeliveryAssignment.partner_id == user.id)
                .order_by(DeliveryAssignmentHistory.created_at.desc())
                .limit(100)
            )
        ).scalars().all()
    )

    base = _build_partner_out(user, profile, active_count, completed_count)
    return DeliveryPartnerDetailOut(
        **base.model_dump(),
        assigned_orders=[
            _build_assignment_out(a, order=order_map.get(a.order_id), partner=user, profile=profile)
            for a in active_rows
        ],
        completed_orders=[
            _build_assignment_out(a, order=order_map.get(a.order_id), partner=user, profile=profile)
            for a in completed_rows
        ],
        assignment_history=[_build_history_out(entry) for entry in hist_rows],
    )


@router.get("/orders/{order_id}/eligible-partners", response_model=list[EligibleDeliveryPartnerOut])
async def get_eligible_partners(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    rows = (
        await db.execute(
            select(User, DeliveryPartnerProfile)
            .join(DeliveryPartnerProfile, DeliveryPartnerProfile.user_id == User.id)
            .where(
                User.role == Role.delivery_partner,
                DeliveryPartnerProfile.deleted_at.is_(None),
            )
            .order_by(User.full_name, User.username)
        )
    ).all()

    partner_ids = [user.id for user, _ in rows]
    active_map, completed_map = await _partner_counts_map(db, partner_ids)
    order_pin = _normalize_pincode(order.shipping_pincode)
    now = datetime.now(timezone.utc)

    result: list[EligibleDeliveryPartnerOut] = []
    for user, profile in rows:
        active = active_map.get(user.id, 0)
        completed = completed_map.get(user.id, 0)
        is_eligible, reasons, remaining_capacity = _evaluate_partner_eligibility(
            user, profile, order_pin, active, now
        )
        pins = _normalize_pincodes(profile.service_pincodes)
        result.append(
            EligibleDeliveryPartnerOut(
                user_id=user.id,
                employee_id=profile.employee_id,
                full_name=user.full_name,
                phone=user.phone,
                email=user.email,
                is_active=user.is_active,
                is_suspended=profile.is_suspended,
                service_area=profile.service_area,
                service_pincodes=pins,
                vehicle_type=profile.vehicle_type,
                vehicle_registration=profile.vehicle_registration,
                max_active_deliveries=profile.max_active_deliveries,
                availability=profile.availability,
                active_assignments=active,
                completed_deliveries=completed,
                remaining_capacity=remaining_capacity,
                is_eligible=is_eligible,
                ineligibility_reason="; ".join(reasons) if reasons else None,
            )
        )

    result.sort(key=lambda p: (not p.is_eligible, -p.remaining_capacity, (p.full_name or "").lower()))
    return result


@router.post("/partners", response_model=DeliveryPartnerOut, status_code=status.HTTP_201_CREATED)
async def create_partner(
    data: DeliveryPartnerCreateIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    username = data.username.strip().lower()
    employee = data.employee_id.strip()
    email = data.email.strip().lower() if data.email and data.email.strip() else None

    if await db.scalar(select(User.id).where(func.lower(User.username) == username)):
        raise HTTPException(status_code=409, detail="Username or delivery partner ID is already in use")
    if email and await db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="Email address is already in use")
    if await db.scalar(select(DeliveryPartnerProfile.user_id).where(DeliveryPartnerProfile.employee_id == employee)):
        raise HTTPException(status_code=409, detail="Username or delivery partner ID is already in use")

    pins = _normalize_pincodes(data.service_pincodes)
    _validate_pincodes(pins)

    user = User(
        role=Role.delivery_partner,
        username=username,
        password_hash=hash_password(data.password),
        email=email,
        full_name=data.full_name.strip(),
        phone=data.phone.strip(),
        is_active=True,
    )
    db.add(user)
    await db.flush()

    profile = DeliveryPartnerProfile(
        user_id=user.id,
        employee_id=employee,
        service_area=data.service_area.strip() if data.service_area and data.service_area.strip() else None,
        service_pincodes=pins,
        vehicle_type=data.vehicle_type.strip() if data.vehicle_type and data.vehicle_type.strip() else None,
        vehicle_registration=data.vehicle_registration.strip() if data.vehicle_registration and data.vehicle_registration.strip() else None,
        max_active_deliveries=data.max_active_deliveries,
        availability=data.availability,
    )
    db.add(profile)
    await db.flush()
    return _build_partner_out(user, profile, 0, 0)


@router.patch("/partners/{partner_id}", response_model=DeliveryPartnerOut)
async def update_partner(
    partner_id: uuid.UUID,
    data: DeliveryPartnerUpdateIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    user, profile = await _lock_partner_and_profile(db, partner_id)
    fields = data.model_fields_set

    if "email" in fields:
        email = data.email.strip().lower() if data.email and data.email.strip() else None
        if email:
            dup = await db.scalar(select(User.id).where(func.lower(User.email) == email, User.id != user.id))
            if dup:
                raise HTTPException(status_code=409, detail="Email address is already in use")
        user.email = email

    if "employee_id" in fields and data.employee_id is not None:
        emp = data.employee_id.strip()
        dup_emp = await db.scalar(
            select(DeliveryPartnerProfile.user_id).where(
                DeliveryPartnerProfile.employee_id == emp,
                DeliveryPartnerProfile.user_id != user.id,
            )
        )
        if dup_emp:
            raise HTTPException(status_code=409, detail="Delivery partner employee ID is already in use")
        profile.employee_id = emp

    if "full_name" in fields and data.full_name is not None:
        user.full_name = data.full_name.strip()
    if "phone" in fields and data.phone is not None:
        user.phone = data.phone.strip()
    if "service_area" in fields:
        profile.service_area = data.service_area.strip() if data.service_area and data.service_area.strip() else None
    if "service_pincodes" in fields and data.service_pincodes is not None:
        pins = _normalize_pincodes(data.service_pincodes)
        _validate_pincodes(pins)
        profile.service_pincodes = pins
    if "vehicle_type" in fields:
        profile.vehicle_type = data.vehicle_type.strip() if data.vehicle_type and data.vehicle_type.strip() else None
    if "vehicle_registration" in fields:
        profile.vehicle_registration = (
            data.vehicle_registration.strip() if data.vehicle_registration and data.vehicle_registration.strip() else None
        )
    if "max_active_deliveries" in fields and data.max_active_deliveries is not None:
        profile.max_active_deliveries = data.max_active_deliveries

    if "is_active" in fields and data.is_active is not None:
        user.is_active = data.is_active
        if not data.is_active:
            profile.availability = "offline"

    if "is_suspended" in fields and data.is_suspended is not None:
        profile.is_suspended = data.is_suspended
        if data.is_suspended:
            profile.availability = "offline"

    if "availability" in fields and data.availability is not None:
        if data.availability == "available" and (not user.is_active or profile.is_suspended):
            raise HTTPException(
                status_code=409,
                detail="Cannot mark an inactive or suspended delivery partner as available",
            )
        profile.availability = data.availability

    now = datetime.now(timezone.utc)
    user.updated_at = now
    profile.updated_at = now
    await db.flush()
    active_count, completed_count = await _single_partner_counts(db, user.id)
    return _build_partner_out(user, profile, active_count, completed_count)


@router.patch("/partners/{partner_id}/active", response_model=DeliveryPartnerOut)
async def set_partner_active(
    partner_id: uuid.UUID,
    active: bool,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    user, profile = await _lock_partner_and_profile(db, partner_id)
    user.is_active = active
    if not active:
        profile.availability = "offline"
    elif not profile.is_suspended:
        profile.availability = "available"
    now = datetime.now(timezone.utc)
    user.updated_at = now
    profile.updated_at = now
    await db.flush()
    active_count, completed_count = await _single_partner_counts(db, user.id)
    return _build_partner_out(user, profile, active_count, completed_count)


@router.patch("/partners/{partner_id}/availability", response_model=DeliveryPartnerOut)
async def set_partner_availability(
    partner_id: uuid.UUID,
    availability: str = Query(..., pattern="^(available|offline)$"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    user, profile = await _lock_partner_and_profile(db, partner_id)
    if availability == "available" and (not user.is_active or profile.is_suspended):
        raise HTTPException(
            status_code=409,
            detail="Cannot mark an inactive or suspended delivery partner as available",
        )
    profile.availability = availability
    profile.updated_at = datetime.now(timezone.utc)
    await db.flush()
    active_count, completed_count = await _single_partner_counts(db, user.id)
    return _build_partner_out(user, profile, active_count, completed_count)


@router.patch("/partners/{partner_id}/suspend", response_model=DeliveryPartnerOut)
async def set_partner_suspended(
    partner_id: uuid.UUID,
    suspended: bool,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    user, profile = await _lock_partner_and_profile(db, partner_id)
    profile.is_suspended = suspended
    if suspended:
        profile.availability = "offline"
    profile.updated_at = datetime.now(timezone.utc)
    await db.flush()
    active_count, completed_count = await _single_partner_counts(db, user.id)
    return _build_partner_out(user, profile, active_count, completed_count)


@router.delete("/partners/{partner_id}", response_model=DeliveryPartnerOut)
async def delete_partner(
    partner_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    user, profile = await _lock_partner_and_profile(db, partner_id)
    active_count, completed_count = await _single_partner_counts(db, user.id)
    if active_count > 0:
        raise HTTPException(
            status_code=409,
            detail="Reassign or complete active deliveries before deleting this delivery partner",
        )
    now = datetime.now(timezone.utc)
    profile.deleted_at = now
    profile.availability = "offline"
    profile.updated_at = now
    user.is_active = False
    user.updated_at = now
    await db.flush()
    return _build_partner_out(user, profile, active_count, completed_count)


@router.get("/assignments", response_model=list[DeliveryAssignmentOut])
async def list_assignments(
    status: str | None = None,
    partner_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
    active_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    stmt = select(DeliveryAssignment)
    if status:
        stmt = stmt.where(DeliveryAssignment.status == status.strip().lower())
    if active_only:
        stmt = stmt.where(DeliveryAssignment.status.in_(ACTIVE_ASSIGNMENTS))
    if partner_id:
        stmt = stmt.where(DeliveryAssignment.partner_id == partner_id)
    if order_id:
        stmt = stmt.where(DeliveryAssignment.order_id == order_id)
    rows = list((await db.execute(stmt.order_by(DeliveryAssignment.assigned_at.desc()).limit(limit))).scalars().all())
    order_ids = list({row.order_id for row in rows})
    order_map = (
        {o.id: o for o in (await db.execute(select(Order).where(Order.id.in_(order_ids)))).scalars().all()}
        if order_ids
        else {}
    )
    return [_build_assignment_out(row, order=order_map.get(row.order_id)) for row in rows]


async def assign(
    order_id: uuid.UUID,
    data: DeliveryAssignmentIn,
    admin: User,
    db: AsyncSession,
    reassign: bool,
    background_tasks: BackgroundTasks | None = None,
) -> DeliveryAssignmentOut:
    now = datetime.now(timezone.utc)
    order = (await db.execute(select(Order).where(Order.id == order_id).with_for_update())).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status in TERMINAL_ORDER_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot assign delivery to an order in '{order.status.value}' status",
        )
    if order.status not in ASSIGNABLE_ORDER_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Delivery can only be assigned to packed or rescheduled failed deliveries",
        )

    current = (
        await db.execute(
            select(DeliveryAssignment)
            .where(
                DeliveryAssignment.order_id == order.id,
                DeliveryAssignment.status.in_(ACTIVE_ASSIGNMENTS),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()

    if current and not reassign:
        raise HTTPException(
            status_code=409,
            detail="Order already has an active delivery assignment; use reassign",
        )
    if current and reassign:
        if current.partner_id == data.partner_id:
            raise HTTPException(
                status_code=409,
                detail="Order is already assigned to this delivery partner",
            )
        old = current.status
        current.status = "cancelled"
        current.version += 1
        current.updated_at = now
        db.add(
            DeliveryAssignmentHistory(
                assignment_id=current.id,
                order_id=order.id,
                actor_id=admin.id,
                from_status=old,
                to_status="cancelled",
                note="Reassigned by administrator",
            )
        )
        db.add(
            OrderNotification(
                order_id=order.id,
                user_id=current.partner_id,
                event_type="delivery_assignment",
                event_key=f"assignment:{current.id}:cancelled:{current.version}",
                channel="in_app",
                recipient=None,
                message=f"Delivery assignment for order {order.order_number} was cancelled",
                payload={"assignment_id": str(current.id), "order_id": str(order.id), "status": "cancelled"},
                status="queued",
            )
        )
        # Flush before inserting the replacement assignment so the partial unique index stays valid.
        await db.flush()
    elif reassign:
        has_prior_assignment = await db.scalar(
            select(DeliveryAssignment.id).where(DeliveryAssignment.order_id == order.id).limit(1)
        )
        if not (order.status == OrderStatus.delivery_failed and has_prior_assignment is not None):
            raise HTTPException(status_code=409, detail="No active assignment to reassign")

    partner = (
        await db.execute(
            select(User)
            .where(User.id == data.partner_id, User.role == Role.delivery_partner)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=422, detail="Choose a valid delivery partner")

    profile = (
        await db.execute(
            select(DeliveryPartnerProfile)
            .where(DeliveryPartnerProfile.user_id == partner.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not profile or profile.deleted_at is not None:
        raise HTTPException(status_code=422, detail="Delivery partner account is unavailable")

    active_count = (
        await db.scalar(
            select(func.count())
            .select_from(DeliveryAssignment)
            .where(
                DeliveryAssignment.partner_id == partner.id,
                DeliveryAssignment.status.in_(ACTIVE_ASSIGNMENTS),
            )
        )
    ) or 0

    order_pin = _normalize_pincode(order.shipping_pincode)
    is_eligible, reasons, _ = _evaluate_partner_eligibility(partner, profile, order_pin, active_count, now)
    if not is_eligible:
        if not partner.is_active:
            raise HTTPException(status_code=422, detail="Choose an active delivery partner")
        if profile.is_suspended or (partner.locked_until is not None and partner.locked_until > now):
            raise HTTPException(status_code=409, detail="Delivery partner account is suspended")
        if (profile.availability or "").strip().lower() != "available":
            raise HTTPException(status_code=409, detail="Delivery partner is not marked available")
        if active_count >= profile.max_active_deliveries:
            raise HTTPException(status_code=409, detail="Delivery partner has reached active delivery capacity")
        if not order_pin or order_pin not in set(_normalize_pincodes(profile.service_pincodes)):
            raise HTTPException(
                status_code=422,
                detail="Order PIN code is outside the partner's configured service area",
            )
        raise HTTPException(status_code=409, detail="; ".join(reasons))

    assignment = DeliveryAssignment(
        order_id=order.id,
        partner_id=partner.id,
        assigned_by=admin.id,
        status="assigned",
        assigned_at=now,
        updated_at=now,
    )
    db.add(assignment)
    await db.flush()

    note = "Reassigned by administrator" if reassign else "Assigned by administrator"
    history_entry = DeliveryAssignmentHistory(
        assignment_id=assignment.id,
        order_id=order.id,
        actor_id=admin.id,
        actor=admin,
        from_status=None,
        to_status="assigned",
        note=note,
        created_at=now,
    )
    db.add(history_entry)

    db.add(
        OrderAuditLog(
            order_id=order.id,
            actor_id=admin.id,
            actor_type="admin",
            action="delivery_reassigned" if reassign else "delivery_assigned",
            event_key=f"delivery-assign:{assignment.id}",
            details={
                "assignment_id": str(assignment.id),
                "partner_id": str(partner.id),
                "partner_name": partner.full_name,
                "order_status": order.status.value,
            },
        )
    )

    in_app_msg = f"New delivery assignment for order {order.order_number} (PIN {order_pin})"
    db.add(
        OrderNotification(
            order_id=order.id,
            user_id=partner.id,
            event_type="delivery_assignment",
            event_key=f"assignment:{assignment.id}:assigned",
            channel="in_app",
            recipient=None,
            message=in_app_msg,
            payload={
                "assignment_id": str(assignment.id),
                "order_id": str(order.id),
                "order_number": order.order_number,
                "shipping_pincode": order_pin,
                "status": "assigned",
            },
            status="queued",
        )
    )

    settings = get_settings()
    email_event_key = f"assignment:{assignment.id}:assigned"
    if partner.email and settings.smtp_configured:
        db.add(
            OrderNotification(
                order_id=order.id,
                user_id=partner.id,
                event_type="delivery_assignment",
                event_key=email_event_key,
                channel="email",
                recipient=partner.email,
                message=(
                    f"Hello {partner.full_name or partner.username},\n\n"
                    f"You have been assigned order {order.order_number} for delivery to PIN {order_pin}.\n"
                    "Please open the DesiDhar Delivery Partner portal to accept and proceed."
                ),
                payload={
                    "assignment_id": str(assignment.id),
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "status": "assigned",
                },
                status="queued",
            )
        )
        if background_tasks is not None and "PYTEST_CURRENT_TEST" not in os.environ:
            background_tasks.add_task(
                dispatch_order_notification,
                str(order.id),
                email_event_key,
                f"New delivery assignment: {order.order_number}",
            )

    order.updated_at = now
    await db.flush()
    await db.refresh(order, attribute_names=["delivery_assignments"])
    await db.refresh(assignment)
    return _build_assignment_out(
        assignment,
        order=order,
        partner=partner,
        profile=profile,
        assigned_by_user=admin,
        history_entries=[history_entry],
    )


@router.post("/orders/{order_id}/assign", response_model=DeliveryAssignmentOut, status_code=201)
async def assign_delivery(
    order_id: uuid.UUID,
    data: DeliveryAssignmentIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await assign(order_id, data, admin, db, False, background_tasks)


@router.post("/orders/{order_id}/reassign", response_model=DeliveryAssignmentOut)
async def reassign_delivery(
    order_id: uuid.UUID,
    data: DeliveryAssignmentIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return await assign(order_id, data, admin, db, True, background_tasks)


@router.get("/orders/{order_id}/assignments", response_model=list[DeliveryAssignmentOut])
async def assignment_history(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    rows = list(
        (
            await db.execute(
                select(DeliveryAssignment)
                .where(DeliveryAssignment.order_id == order_id)
                .order_by(DeliveryAssignment.assigned_at.desc())
            )
        ).scalars().all()
    )
    return [_build_assignment_out(row, order=order) for row in rows]


@router.get("/settlements", response_model=list[CashSettlementOut])
async def list_settlements(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    return list(
        (await db.execute(select(CashSettlement).order_by(CashSettlement.submitted_at.desc()).limit(200))).scalars().all()
    )


@router.post("/settlements/{settlement_id}/reconcile", response_model=CashSettlementOut)
async def reconcile_settlement(
    settlement_id: uuid.UUID,
    data: CashSettlementReconcileIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    settlement = (
        await db.execute(select(CashSettlement).where(CashSettlement.id == settlement_id).with_for_update())
    ).scalar_one_or_none()
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
async def approve_settlement(
    settlement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    settlement = (
        await db.execute(select(CashSettlement).where(CashSettlement.id == settlement_id).with_for_update())
    ).scalar_one_or_none()
    if not settlement:
        raise HTTPException(status_code=404, detail="Cash settlement not found")
    if settlement.status != "approved" or settlement.verified_amount_paise != settlement.expected_amount_paise:
        raise HTTPException(status_code=409, detail="Record and verify the full deposited amount before approval")
    settlement.reviewed_by = admin.id
    await db.flush()
    return settlement


@router.post("/settlements/{settlement_id}/reject", response_model=CashSettlementOut)
async def reject_settlement(
    settlement_id: uuid.UUID,
    data: CashSettlementRejectIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    settlement = (
        await db.execute(select(CashSettlement).where(CashSettlement.id == settlement_id).with_for_update())
    ).scalar_one_or_none()
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
