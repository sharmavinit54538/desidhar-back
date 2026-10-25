from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.services.auth_service import authenticate_admin
from app.core.tokens import create_admin_token
from app.schemas.auth import AdminLogin, TokenResponse

router = APIRouter(prefix="/admin/auth", tags=["admin"])


@router.post("/login", response_model=TokenResponse)
async def admin_login(data: AdminLogin, db: AsyncSession = Depends(get_db)):
    user = await authenticate_admin(db, data.username, data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.locked_until:
        from app.core.clock import utc_now
        if user.locked_until > utc_now():
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Account locked, try again later")

    token = create_admin_token(str(user.id))
    return TokenResponse(access_token=token, expires_in=30 * 60)