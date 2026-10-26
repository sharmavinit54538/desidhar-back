import uuid
from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.order import OrderCreateIn, OrderOut, OrderListOut, CancelOrderIn
from app.services.order_service import (
    place_order, get_user_order, list_user_orders, transition_order_status,
)

from sqlalchemy import delete
from app.models.cart_item import CartItem
from app.services.cart_service import get_or_create_cart

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    data: OrderCreateIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    key = (idempotency_key or str(uuid.uuid4())).strip()
    if data.items:
        cart = await get_or_create_cart(db, user.id)
        await db.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
        for it in data.items:
            db.add(CartItem(cart_id=cart.id, product_id=it.product_id, quantity=it.quantity))
        await db.flush()

    order, err = await place_order(db, user, data.address_id, data.payment_method, key, data.coupon_code, data.notes)
    if err or not order:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err or "Could not place order")
    return order



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

