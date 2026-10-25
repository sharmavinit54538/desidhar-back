from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.services.otp_service import create_otp, verify_otp
from app.services.email_service import send_otp_email
from app.services.auth_service import get_or_create_customer
from app.core.tokens import create_customer_token
from app.schemas.auth import OTPRequest, OTPVerify, TokenResponse

router = APIRouter(prefix="/auth/otp", tags=["auth"])


@router.post("/request", status_code=status.HTTP_202_ACCEPTED)
async def request_otp(
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


@router.post("/verify", response_model=TokenResponse)
async def verify_otp_endpoint(data: OTPVerify, db: AsyncSession = Depends(get_db)):
    valid = await verify_otp(db, data.email, data.otp)
    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired OTP")

    user = await get_or_create_customer(db, data.email)
    token = create_customer_token(str(user.id))
    return TokenResponse(access_token=token, expires_in=7 * 24 * 60 * 60)