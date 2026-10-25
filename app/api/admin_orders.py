import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, require_admin
from app.models.user import User
from app.models.order import Order
from app.schemas.order import OrderOut, OrderListOut, OrderStatusUpdateIn
from app.schemas.refund import RefundCreateIn, RefundOut
from app.services.order_service import admin_list_orders, transition_order_status
from app.services.refund_service import create_refund, list_order_refunds
from app.services.payment_service import cancel_expired_unpaid_orders

router = APIRouter(prefix="/admin/orders", tags=["admin-orders"])


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
    ok, err = await transition_order_status(db, order, data.status, changed_by=admin.id, note=data.note, is_admin=True)
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err)
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

