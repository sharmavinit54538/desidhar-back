import uuid
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.order import Order
from app.schemas.payment import PaymentInitiateOut, PaymentVerifyIn
from app.schemas.order import OrderOut
from app.services.payment_service import initiate_payment, verify_payment, process_webhook

router = APIRouter(tags=["payments"])


@router.post("/orders/{order_id}/pay", response_model=PaymentInitiateOut)
async def start_payment(order_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Order).where(Order.id == order_id, Order.user_id == user.id)
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    data = await initiate_payment(db, order)
    return PaymentInitiateOut(**data)


@router.post("/payments/verify", response_model=OrderOut)
async def verify(data: PaymentVerifyIn, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    ok, order = await verify_payment(db, data.model_dump())
    if not ok or not order:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment verification failed")
    return order


@router.post("/payments/webhook")
async def webhook(
    request: Request,
    signature: str = Header(..., alias="X-Signature"),
    db: AsyncSession = Depends(get_db),
):
    payload = await request.json()
    ok, order = await process_webhook(db, payload, signature)
    if not ok or not order:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature or payload")
    return {"status": "success", "order_id": order.id, "order_status": order.status.value}
