import hmac
import hashlib
import secrets
from datetime import timedelta
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.clock import utc_now
from app.core.config import get_settings
from app.models.otp import OTPCode

settings = get_settings()
OTP_TTL = timedelta(minutes=5)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=60)


def _hash_otp(otp: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), otp.encode(), hashlib.sha256).hexdigest()


def _generate_otp() -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(6))


async def create_otp(session: AsyncSession, email: str) -> str:
    email_lower = email.lower().strip()

    await session.execute(delete(OTPCode).where(OTPCode.email == email_lower))

    result = await session.execute(
        select(OTPCode).where(OTPCode.email == email_lower).order_by(OTPCode.created_at.desc()).limit(1)
    )
    last_otp = result.scalar_one_or_none()
    if last_otp and utc_now() - last_otp.created_at < RESEND_COOLDOWN:
        raise ValueError("cooldown")

    otp = _generate_otp()
    code_hash = _hash_otp(otp)
    expires_at = utc_now() + OTP_TTL

    otp_code = OTPCode(email=email_lower, code_hash=code_hash, expires_at=expires_at)
    session.add(otp_code)
    await session.flush()
    return otp


async def verify_otp(session: AsyncSession, email: str, otp: str) -> bool:
    email_lower = email.lower().strip()
    code_hash = _hash_otp(otp)

    result = await session.execute(
        select(OTPCode)
        .where(OTPCode.email == email_lower, OTPCode.consumed_at.is_(None))
        .order_by(OTPCode.created_at.desc())
        .limit(1)
    )
    otp_code = result.scalar_one_or_none()

    if not otp_code:
        return False

    if utc_now() > otp_code.expires_at:
        return False

    if not hmac.compare_digest(otp_code.code_hash, code_hash):
        otp_code.attempts += 1
        if otp_code.attempts >= MAX_ATTEMPTS:
            await session.delete(otp_code)
        return False

    otp_code.consumed_at = utc_now()
    return True