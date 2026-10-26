from fastapi import APIRouter, Depends, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.schemas.payment_method import PaymentMethodOut
from app.services.payment_method_service import list_payment_methods

router = APIRouter(prefix="/payments/methods", tags=["payments"])


@router.get("", response_model=list[PaymentMethodOut])
async def get_payment_methods(
    order_total: float | None = Query(default=None, ge=0),
    pincode: str | None = Query(default=None),
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    return await list_payment_methods(db, order_total=order_total, pincode=pincode, enabled_only=True)
