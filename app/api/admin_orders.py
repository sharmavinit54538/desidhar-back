import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, require_admin
from app.models.user import User
from app.models.order import Order, OrderStatus, PaymentMethod, PaymentStatus
from app.models.delivery_management import DeliveryAssignment
from app.models.delivery_finance import DeliveryOTP
from app.schemas.order import OrderOut, OrderListOut, OrderStatusUpdateIn, OrderSummaryOut, DeliveryDetailsUpdateIn
from app.schemas.refund import RefundCreateIn, RefundOut
from app.services.order_service import admin_list_orders, transition_order_status
from app.services.refund_service import create_refund, list_order_refunds
from app.services.payment_service import cancel_expired_unpaid_orders
from app.models.order_lifecycle import Shipment, OrderNotification
from app.services.email_service import send_order_email
from fastapi import BackgroundTasks

router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])


@router.get("/summary", response_model=OrderSummaryOut)
async def order_summary(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    from app.models.order import OrderStatus, PaymentMethod, PaymentStatus
    from app.models.refund import Refund
    statuses = (await db.execute(select(Order.status, func.count()).group_by(Order.status))).all()
    counts = {str(s.value if hasattr(s, "value") else s): n for s, n in statuses}
    refunds = await db.scalar(select(func.count()).select_from(Refund).where(Refund.status == "pending")) or 0
    cod_q = select(func.count(), func.coalesce(func.sum(Order.total_paise), 0)).where(
        Order.payment_method == PaymentMethod.cod, Order.payment_status != PaymentStatus.paid,
        Order.status == OrderStatus.delivered)
    cod_count, cod_amount = (await db.execute(cod_q)).one()
    return OrderSummaryOut(
        total_orders=sum(counts.values()), new_orders=counts.get("placed", 0),
        confirmed_orders=counts.get("confirmed", 0), pending_packing=counts.get("confirmed", 0),
        packed_orders=counts.get("packed", 0), shipped_orders=counts.get("shipped", 0),
        out_for_delivery=counts.get("out_for_delivery", 0), delivered_orders=counts.get("delivered", 0),
        cancelled_orders=counts.get("cancelled", 0), failed_deliveries=counts.get("delivery_failed", 0),
        return_requests=counts.get("return_requested", 0), pending_refunds=refunds,
        pending_cod_collection=cod_count, pending_cod_amount_paise=cod_amount)


@router.get("", response_model=OrderListOut)
async def list_orders(
    status: str | None = None,
    payment_method: str | None = None,
    payment_status: str | None = None,
    pincode: str | None = None,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    if status and status.strip().lower() not in OrderStatus._value2member_map_:
        raise HTTPException(status_code=422, detail=f"Unsupported fulfillment status '{status}'. Use an explicit status such as placed or payment_pending.")
    if payment_method and payment_method.strip().lower() not in PaymentMethod._value2member_map_:
        raise HTTPException(status_code=422, detail=f"Unsupported payment method '{payment_method}'.")
    if payment_status and payment_status.strip().lower() not in PaymentStatus._value2member_map_:
        raise HTTPException(status_code=422, detail=f"Unsupported payment status '{payment_status}'.")
    items, total = await admin_list_orders(db, status, payment_method, payment_status, pincode, q, page, page_size)
    return OrderListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order_detail(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.post("/{order_id}/status", response_model=OrderOut)
async def change_status(
    order_id: uuid.UUID, data: OrderStatusUpdateIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin),
):
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if data.status == OrderStatus.delivered.value:
        active_assignment = (await db.execute(select(DeliveryAssignment).where(
            DeliveryAssignment.order_id == order_id,
            DeliveryAssignment.status.in_(("assigned", "accepted", "picked_up", "in_progress"))
        ))).scalar_one_or_none()
        if active_assignment:
            verified_otp = await db.scalar(select(DeliveryOTP.id).where(
                DeliveryOTP.order_id == order_id, DeliveryOTP.assignment_id == active_assignment.id,
                DeliveryOTP.used_at.is_not(None)).limit(1))
            if not verified_otp:
                raise HTTPException(status_code=409, detail="An assigned delivery can only be completed after the delivery partner verifies the customer OTP")
            if order.payment_status != PaymentStatus.paid:
                raise HTTPException(status_code=409, detail="Payment must be verified before completing delivery")
    ok, err = await transition_order_status(db, order, data.status, changed_by=admin.id, note=data.note, is_admin=True, expected_version=data.expected_version)
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err)
    return order


@router.patch("/{order_id}/delivery", response_model=OrderOut)
async def update_delivery_details(
    order_id: uuid.UUID, data: DeliveryDetailsUpdateIn, background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin),
):
    order = (await db.execute(select(Order).where(Order.id == order_id).with_for_update())).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    fields = data.model_fields_set
    for name in ("estimated_delivery_date", "estimated_delivery_end_date", "revised_delivery_date", "delay_reason"):
        if name in fields:
            setattr(order, name, getattr(data, name))
    if "courier_name" in fields or "tracking_number" in fields or "tracking_url" in fields:
        shipment = order.shipment
        if shipment is None:
            shipment = Shipment(order_id=order.id, courier_name=data.courier_name or "Courier pending",
                                shipment_reference=order.order_number, shipment_status=order.status.value,
                                shipped_at=order.shipped_at or datetime.now(timezone.utc))
            db.add(shipment)
        if data.courier_name is not None:
            shipment.courier_name = data.courier_name
        if "tracking_number" in fields:
            shipment.tracking_number = data.tracking_number
        if "tracking_url" in fields:
            shipment.tracking_url = data.tracking_url
    revised = data.revised_delivery_date
    original = order.estimated_delivery_date
    if revised and original and revised > original and data.delay_reason and order.customer_email:
        message = f"Your order {order.order_number} is delayed. Revised expected delivery: {revised.isoformat()}. Reason: {data.delay_reason}. Track your order in My Orders."
        event_key = f"delivery-delay:{revised.isoformat()}"
        db.add(OrderNotification(order_id=order.id, user_id=order.user_id, event_type="delivery_delay",
                                 event_key=event_key, channel="email", recipient=order.customer_email,
                                 message=message, payload={"revised_delivery_date": revised.isoformat(), "reason": data.delay_reason}, status="queued"))
        background_tasks.add_task(send_order_email, order.customer_email, f"Delivery update for {order.order_number}", message)
    await db.flush()
    await db.refresh(order)
    return order


@router.post("/{order_id}/mark-paid", response_model=OrderOut)
async def mark_order_paid(
    order_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin),
):
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    from datetime import datetime, timezone
    from app.models.order import PaymentStatus
    from app.models.payment import Payment
    now = datetime.now(timezone.utc)
    order.payment_status = PaymentStatus.paid
    for p in order.payments:
        p.status = PaymentStatus.paid
        p.paid_at = now
    await db.flush()
    await db.refresh(order)
    return order


@router.post("/{order_id}/refunds", response_model=RefundOut, status_code=status.HTTP_201_CREATED)
async def refund_order(
    order_id: uuid.UUID, data: RefundCreateIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin),
):
    ref, err = await create_refund(db, admin.id, order_id, data.order_item_id, data.amount_paise, data.reason, data.restock, data.notes)
    if err or not ref:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err or "Could not issue refund")
    return ref


@router.get("/{order_id}/refunds", response_model=list[RefundOut])
async def get_refunds(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    return await list_order_refunds(db, order_id)


@router.post("/cancel-expired")
async def cancel_expired(timeout_minutes: int = 30, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    count = await cancel_expired_unpaid_orders(db, timeout_minutes)
    return {"cancelled_count": count}

