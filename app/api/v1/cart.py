import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import (
    get_optional_current_user,
    get_current_user,
    get_guest_session_id,
)
from app.models.user import User
from app.schemas.cart import (
    CartResponse,
    CartItemAdd,
    CartItemUpdate,
    MergeCartRequest,
)
from app.services.cart_service import cart_service

router = APIRouter(prefix="/cart", tags=["Cart & Guest Merging"])


def _ensure_guest_session(request: Request, response: Response) -> str:
    sid = get_guest_session_id(request)
    if not sid:
        sid = f"guest_{uuid.uuid4().hex}"
        response.set_cookie(
            key="guest_session_id",
            value=sid,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 7,  # 7 days
            path="/",
        )
    return sid


@router.get(
    "",
    response_model=CartResponse,
    summary="Get current shopping cart (guest Redis cart or authenticated DB cart)",
)
async def get_cart(
    request: Request,
    response: Response,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user:
        return await cart_service.get_user_cart(db, current_user.id)
    sid = _ensure_guest_session(request, response)
    return await cart_service.get_guest_cart(db, sid)


@router.post(
    "/items",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
    summary="Add product to cart",
)
async def add_item_to_cart(
    data: CartItemAdd,
    request: Request,
    response: Response,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user:
        return await cart_service.add_to_user_cart(
            db,
            user_id=current_user.id,
            product_id=data.product_id,
            quantity=data.quantity,
        )
    sid = _ensure_guest_session(request, response)
    return await cart_service.add_to_guest_cart(
        db,
        session_id=sid,
        product_id=data.product_id,
        quantity=data.quantity,
    )


@router.patch(
    "/items/{product_id}",
    response_model=CartResponse,
    summary="Update item quantity in cart",
)
async def update_cart_item(
    product_id: uuid.UUID,
    data: CartItemUpdate,
    request: Request,
    response: Response,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user:
        return await cart_service.update_user_cart_item(
            db,
            user_id=current_user.id,
            product_id=product_id,
            quantity=data.quantity,
        )
    sid = _ensure_guest_session(request, response)
    return await cart_service.update_guest_cart_item(
        db,
        session_id=sid,
        product_id=product_id,
        quantity=data.quantity,
    )


@router.delete(
    "/items/{product_id}",
    response_model=CartResponse,
    summary="Remove item from cart",
)
async def remove_cart_item(
    product_id: uuid.UUID,
    request: Request,
    response: Response,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user:
        return await cart_service.remove_user_cart_item(
            db,
            user_id=current_user.id,
            product_id=product_id,
        )
    sid = _ensure_guest_session(request, response)
    return await cart_service.remove_guest_cart_item(
        db,
        session_id=sid,
        product_id=product_id,
    )


@router.post(
    "/merge",
    response_model=CartResponse,
    summary="Explicitly merge guest cart into authenticated user cart",
)
async def merge_cart(
    data: MergeCartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await cart_service.merge_guest_cart_into_user_cart(
        db,
        user_id=current_user.id,
        guest_session_id=data.guest_session_id,
    )
