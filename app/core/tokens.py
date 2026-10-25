from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from app.core.config import get_settings

settings = get_settings()


def create_access_token(sub: str, role: str, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": sub, "role": role, "iat": int(now.timestamp()), "exp": int(expire.timestamp())}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_customer_token(sub: str) -> str:
    return create_access_token(sub, "customer", timedelta(days=settings.CUSTOMER_TOKEN_EXPIRE_DAYS))


def create_admin_token(sub: str) -> str:
    return create_access_token(sub, "admin", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], options={"require_exp": True, "require_sub": True})
        return payload
    except JWTError:
        raise ValueError("Invalid token")