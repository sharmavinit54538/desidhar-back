import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.cart import CartOut, CartItemUpdateIn
from app.services.cart_service import get_cart_view, update_cart_item, clear_cart

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("", response_model=CartOut)
async def view_cart(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await get_cart_view(db, user.id)


@router.put("/items/{product_id}", response_model=CartOut)
async def set_item_qty(
    product_id: uuid.UUID, data: CartItemUpdateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    ok, err = await update_cart_item(db, user.id, product_id, data.quantity)
    if not ok:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err)
    return await get_cart_view(db, user.id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def empty_cart(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await clear_cart(db, user.id)
