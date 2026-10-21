from typing import Optional
from fastapi import APIRouter, Request, Header, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.payment_service import payment_service

router = APIRouter(prefix="/webhooks", tags=["Payment Webhooks & Idempotency"])


@router.post(
    "/razorpay",
    status_code=status.HTTP_200_OK,
    summary="Razorpay webhook with HMAC-SHA256 signature verification & idempotency",
)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    db: AsyncSession = Depends(get_db),
):
    raw_body = await request.body()
    result = await payment_service.handle_razorpay_webhook(
        db=db,
        raw_body=raw_body,
        signature=x_razorpay_signature,
    )
    return result


@router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
    summary="Stripe webhook with signature verification & idempotency",
)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    raw_body = await request.body()
    result = await payment_service.handle_stripe_webhook(
        db=db,
        raw_body=raw_body,
        sig_header=stripe_signature,
    )
    return result
