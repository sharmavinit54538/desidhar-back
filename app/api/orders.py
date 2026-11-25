import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.order import PaymentMethod
from app.schemas.order import OrderCreateIn, OrderOut, OrderListOut, CancelOrderIn, PlaceOrderResponse, CustomerReturnIn, OrderTrackingOut
from app.services.order_service import (
    place_order, get_order_by_idempotency, get_user_order, list_user_orders, transition_order_status,
)
from app.services.payment_service import initiate_payment

from app.models.cart_item import CartItem
from app.models.payment import Payment
from app.services.cart_service import get_or_create_cart
from app.services.email_service import dispatch_order_notification

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=PlaceOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    data: OrderCreateIn,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    key = (idempotency_key or str(uuid.uuid4())).strip()

    # Serialize order submissions before touching the cart. A retry after a
    # successful checkout must return that order without restoring its items.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    existing_order = await get_order_by_idempotency(db, user.id, key)
    if existing_order:
        payment_url = None
        if existing_order.payment_method == PaymentMethod.online:
            payment = await db.scalar(select(Payment).where(Payment.order_id == existing_order.id))
            if payment and payment.provider_order_id:
                payment_url = f"/payments/checkout?order_id={existing_order.id}&provider_order_id={payment.provider_order_id}"
            elif payment and payment.status.value != "paid":
                payment_data = await initiate_payment(db, existing_order)
                payment_url = f"/payments/checkout?order_id={existing_order.id}&provider_order_id={payment_data['provider_order_id']}"
        return PlaceOrderResponse(order=existing_order, payment_url=payment_url)

    if data.items:
        cart = await get_or_create_cart(db, user.id)
        requested: dict[uuid.UUID, int] = {}
        for it in data.items:
            requested[it.product_id] = requested.get(it.product_id, 0) + it.quantity

        existing_items = {item.product_id: item for item in cart.items}
        for product_id, item in existing_items.items():
            quantity = requested.pop(product_id, None)
            if quantity is None:
                cart.items.remove(item)
            else:
                item.quantity = quantity
        for product_id, quantity in requested.items():
            cart.items.append(CartItem(product_id=product_id, quantity=quantity))
        await db.flush()

    order, err = await place_order(db, user, data.address_id, data.payment_method, key, data.coupon_code, data.notes, data.delivery_speed)
    if err or not order:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err or "Could not place order")

    if order.customer_email:
        background_tasks.add_task(dispatch_order_notification, str(order.id), "order-confirmation-email",
                                  f"Order {order.order_number} confirmed")

    payment_url = None
    if order.payment_method == PaymentMethod.online:
        payment_data = await initiate_payment(db, order)
        payment_url = f"/payments/checkout?order_id={order.id}&provider_order_id={payment_data['provider_order_id']}"

    return PlaceOrderResponse(order=order, payment_url=payment_url)



@router.get("", response_model=OrderListOut)
async def list_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total = await list_user_orders(db, user.id, page, page_size)
    return OrderListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    order = await get_user_order(db, user.id, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.get("/{order_id}/tracking", response_model=OrderTrackingOut)
async def track_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    order = await get_user_order(db, user.id, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    shipment = order.shipment
    return OrderTrackingOut(
        order_id=order.id, order_number=order.order_number, status=order.status.value,
        delivery_status=order.delivery_status, order_date=order.placed_at or order.created_at,
        estimated_delivery_date=order.estimated_delivery_date,
        estimated_delivery_end_date=order.estimated_delivery_end_date,
        revised_delivery_date=order.revised_delivery_date, actual_delivery_date=order.delivered_at,
        delay_reason=order.delay_reason, shipping_pincode=order.shipping_pincode,
        courier_name=shipment.courier_name if shipment else None,
        tracking_id=shipment.tracking_number if shipment else None,
        tracking_url=shipment.tracking_url if shipment else None, timeline=order.history,
    )


@router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: uuid.UUID, data: CancelOrderIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    order = await get_user_order(db, user.id, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    ok, err = await transition_order_status(db, order, "cancelled", changed_by=user.id, note=data.reason, is_admin=False)
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err)
    return order


@router.post("/{order_id}/return-request", response_model=OrderOut)
async def request_return(order_id: uuid.UUID, data: CustomerReturnIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    order = await get_user_order(db, user.id, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status.value != "delivered":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Returns can only be requested for delivered orders")
    ok, err = await transition_order_status(db, order, "return_requested", changed_by=user.id, note=data.reason)
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err)
    return order

