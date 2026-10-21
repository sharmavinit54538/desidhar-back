from typing import Optional
from fastapi import APIRouter, Depends, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    RoleChecker,
    get_guest_session_id,
)
from app.core.exceptions import UnauthorizedException
from app.models.user import User, UserRole
from app.schemas.auth import (
    UserRegisterRequest,
    StaffCreateRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
)
from app.services.auth_service import auth_service
from app.services.cart_service import cart_service

router = APIRouter(prefix="/auth", tags=["Authentication & RBAC"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Public customer registration",
)
async def register(
    data: UserRegisterRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Register customer
    user = await auth_service.register_customer(db, data)

    # Automatically authenticate
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user, access_token, refresh_token = await auth_service.authenticate(
        db,
        UserLoginRequest(email=data.email, password=data.password),
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # Attach secure HTTP-Only cookies
    auth_service.set_auth_cookies(response, access_token, refresh_token)

    # Auto-merge guest cart if guest_session_id provided
    guest_sid = data.guest_session_id or get_guest_session_id(request)
    if guest_sid:
        await cart_service.merge_guest_cart_into_user_cart(db, user.id, guest_sid)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=900,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User login with HTTP-Only cookie setting & guest cart merge",
)
async def login(
    data: UserLoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user, access_token, refresh_token = await auth_service.authenticate(
        db,
        data,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    auth_service.set_auth_cookies(response, access_token, refresh_token)

    # Auto-merge guest cart items into authenticated user's cart
    guest_sid = data.guest_session_id or get_guest_session_id(request)
    if guest_sid:
        await cart_service.merge_guest_cart_into_user_cart(db, user.id, guest_sid)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=900,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Token rotation & reuse detection",
)
async def refresh_token_endpoint(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        # Fallback to custom header or body if needed
        auth_header = request.headers.get("X-Refresh-Token")
        if auth_header:
            refresh_token = auth_header

    if not refresh_token:
        raise UnauthorizedException("Refresh token missing from cookie or header")

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user, new_access_token, new_refresh_token = await auth_service.refresh_tokens(
        db,
        refresh_token=refresh_token,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    auth_service.set_auth_cookies(response, new_access_token, new_refresh_token)

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=900,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout and revoke current session",
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    refresh_token = request.cookies.get("refresh_token")
    await auth_service.logout(db, refresh_token)
    auth_service.clear_auth_cookies(response)
    return {"message": "Successfully logged out and session revoked"}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.post(
    "/me/revoke-all-sessions",
    status_code=status.HTTP_200_OK,
    summary="Revoke all active user sessions",
)
async def revoke_all_sessions(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.revoke_all_user_sessions(db, current_user.id)
    auth_service.clear_auth_cookies(response)
    return {"message": "All active sessions have been terminated"}


# ------------------ SUPER_ADMIN STAFF MANAGEMENT ------------------

@router.post(
    "/admin/staff",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RoleChecker([UserRole.SUPER_ADMIN]))],
    summary="Create staff members with granular permissions (SUPER_ADMIN only)",
)
async def create_staff_endpoint(
    data: StaffCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    staff_user = await auth_service.create_staff(db, data)
    return UserResponse.model_validate(staff_user)
