import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    RoleChecker,
    PermissionChecker,
)
from app.core.exceptions import ForbiddenException
from app.models.user import User, UserRole
from app.models.order import OrderStatus, PaymentStatus
from app.schemas.order import (
    OrderCreate,
    OrderResponse,
    OrderStatusUpdate,
    OrderRefundRequest,
)
from app.schemas.payment import PaymentOrderInitResponse
from app.schemas.common import PaginatedResponse
from app.services.order_service import order_service
from app.services.payment_service import payment_service

router = APIRouter(prefix="/orders", tags=["Order Lifecycle & Concurrency"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Checkout cart: Atomic row-level inventory lock & order creation",
)
async def checkout(
    data: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.create_order_from_cart(
        db=db,
        customer=current_user,
        shipping_address=data.shipping_address,
        payment_gateway=data.payment_gateway,
    )
    return OrderResponse.model_validate(order)


@router.get(
    "",
    response_model=PaginatedResponse[OrderResponse],
    summary="List orders (Customers see own; Staff/Admin see all)",
)
async def list_orders(
    customer_id: Optional[uuid.UUID] = Query(None, description="Filter by customer ID (Staff only)"),
    order_status: Optional[OrderStatus] = Query(None, description="Filter by order status"),
    payment_status: Optional[PaymentStatus] = Query(None, description="Filter by payment status"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    orders, total = await order_service.list_orders(
        db=db,
        current_user=current_user,
        customer_id=customer_id,
        order_status=order_status,
        payment_status=payment_status,
        page=page,
        size=size,
    )
    pages = (total + size - 1) // size if total > 0 else 0
    return PaginatedResponse(
        items=[OrderResponse.model_validate(o) for o in orders],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get(
    "/{id}",
    response_model=OrderResponse,
    summary="Get order details by ID",
)
async def get_order_by_id(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order_by_id(db, id)

    # Access control: Customer can only view their own order
    if current_user.role == UserRole.CUSTOMER and order.customer_id != current_user.id:
        raise ForbiddenException("You cannot access another user's order details")

    return OrderResponse.model_validate(order)


@router.post(
    "/{id}/cancel",
    response_model=OrderResponse,
    summary="Cancel order and rollback inventory stock",
)
async def cancel_order(
    id: uuid.UUID,
    refund_data: Optional[OrderRefundRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reason = refund_data.reason if refund_data else "User requested cancellation"
    order = await order_service.cancel_order(db, id, current_user, reason=reason)
    return OrderResponse.model_validate(order)


@router.patch(
    "/{id}/status",
    response_model=OrderResponse,
    dependencies=[
        Depends(RoleChecker([UserRole.SUPER_ADMIN, UserRole.STORE_MANAGER, UserRole.SUPPORT_STAFF])),
    ],
    summary="Update order progression status (Staff/Admin)",
)
async def update_order_status(
    id: uuid.UUID,
    data: OrderStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.update_order_status(db, id, data.order_status, current_user)
    return OrderResponse.model_validate(order)


@router.post(
    "/{id}/pay",
    response_model=PaymentOrderInitResponse,
    summary="Initialize gateway payment order (Razorpay / Stripe)",
)
async def initiate_payment(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await order_service.get_order_by_id(db, id)

    if current_user.role == UserRole.CUSTOMER and order.customer_id != current_user.id:
        raise ForbiddenException("Cannot pay for another user's order")

    result = await payment_service.initialize_payment(db, order)
    return PaymentOrderInitResponse(**result)
