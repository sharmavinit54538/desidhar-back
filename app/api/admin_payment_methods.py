from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, require_admin
from app.models.user import User
from app.schemas.payment_method import PaymentMethodOut, PaymentMethodUpdateIn
from app.services.payment_method_service import list_payment_methods, update_payment_method

router = APIRouter(prefix="/admin/payments/methods", tags=["admin-payments"])


@router.get("", response_model=list[PaymentMethodOut])
async def admin_list_methods(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    return await list_payment_methods(db, enabled_only=False)


@router.patch("/{method_id}", response_model=PaymentMethodOut)
async def admin_patch_method(
    method_id: str,
    data: PaymentMethodUpdateIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    updated = await update_payment_method(db, method_id, data.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment method not found")
    return PaymentMethodOut(
        id=updated.id, code=updated.code, name=updated.name, label=updated.name,
        type=updated.type, enabled=updated.enabled, description=updated.description,
        icon=updated.icon, min_order=updated.min_order, max_order=updated.max_order,
        sort_order=updated.sort_order,
    )
