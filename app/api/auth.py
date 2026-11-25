import logging
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.services.otp_service import create_otp, verify_otp
from app.services.email_service import send_otp_email
from app.services.auth_service import get_or_create_customer, get_user_by_id
from app.core.tokens import create_customer_token, create_admin_token, create_access_token, create_refresh_token, decode_refresh_token
from app.schemas.auth import OTPRequest, OTPVerify, TokenResponse, RefreshTokenRequest
from app.core.rate_limit import limiter
from app.core.config import get_settings
from app.models.user import Role, User

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth/otp", tags=["auth"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def request_otp(
    request: Request,
    data: OTPRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    try:
        otp = await create_otp(db, data.email)
        background_tasks.add_task(send_otp_email, data.email, otp)
    except ValueError as e:
        if str(e) == "cooldown":
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Please wait before requesting another OTP")
        raise
    return {"message": "If the email exists, an OTP has been sent"}


@router.post("/resend", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def resend_otp(
    request: Request,
    data: OTPRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    return await request_otp(request=request, data=data, background_tasks=background_tasks, db=db)


@router.post("/verify", response_model=TokenResponse)
@limiter.limit("10/minute")
async def verify_otp_endpoint(request: Request, data: OTPVerify, db: AsyncSession = Depends(get_db)):
    valid = await verify_otp(db, data.email, data.otp)
    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired OTP")

    try:
        user = await get_or_create_customer(db, data.email)
    except Exception as e:
        logger.error("Database error during customer creation: %s", type(e).__name__)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to authenticate user due to database error",
        )

    if user.role != Role.customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts must authenticate via admin login",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    token = create_customer_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id), "customer")
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.CUSTOMER_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        refresh_token=refresh_token,
    )


@auth_router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh_token_endpoint(
    request: Request,
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_refresh_token(data.refresh_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    user_id = payload.get("sub")
    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    if user.role == Role.customer:
        new_access_token = create_customer_token(str(user.id))
    elif user.role == Role.admin:
        new_access_token = create_admin_token(str(user.id))
    elif user.role == Role.delivery_partner:
        new_access_token = create_access_token(str(user.id), "delivery_partner")
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unsupported account role")
    new_refresh_token = create_refresh_token(str(user.id), user.role.value)
    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.CUSTOMER_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        refresh_token=new_refresh_token,
    )


@auth_router.post("/logout")
async def logout_endpoint(request: Request):
    return {"message": "Successfully logged out"}
