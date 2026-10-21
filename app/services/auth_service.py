import uuid
from typing import Optional, Tuple, List
from datetime import datetime, timedelta, timezone
from fastapi import Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    hash_token,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.exceptions import (
    BadRequestException,
    UnauthorizedException,
    ConflictException,
    TokenReuseDetectedException,
)
from app.models.user import User, UserSession, UserRole, UserStatus
from app.schemas.auth import UserRegisterRequest, StaffCreateRequest, UserLoginRequest
from app.services.notification_service import notification_service


class AuthService:

    @staticmethod
    def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
        """
        Attaches HTTP-Only, Secure, SameSite='Lax' cookies to the response.
        """
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
            domain=settings.COOKIE_DOMAIN,
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            path="/api/v1/auth/refresh",
            domain=settings.COOKIE_DOMAIN,
        )

    @staticmethod
    def clear_auth_cookies(response: Response) -> None:
        """
        Clears authentication cookies.
        """
        response.delete_cookie(
            key="access_token",
            path="/",
            domain=settings.COOKIE_DOMAIN,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
        )
        response.delete_cookie(
            key="refresh_token",
            path="/api/v1/auth/refresh",
            domain=settings.COOKIE_DOMAIN,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
        )

    @classmethod
    async def register_customer(
        cls,
        db: AsyncSession,
        data: UserRegisterRequest,
    ) -> User:
        """
        Public registration for CUSTOMER accounts only.
        """
        existing = await db.execute(select(User).where(User.email == data.email.lower()))
        if existing.scalar_one_or_none():
            raise ConflictException("A user with this email address already exists")

        user = User(
            email=data.email.lower(),
            hashed_password=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            role=UserRole.CUSTOMER,
            status=UserStatus.ACTIVE,
            permissions=[],
            is_verified=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @classmethod
    async def create_staff(
        cls,
        db: AsyncSession,
        data: StaffCreateRequest,
    ) -> User:
        """
        Staff creation strictly for SUPER_ADMIN with custom permissions.
        """
        existing = await db.execute(select(User).where(User.email == data.email.lower()))
        if existing.scalar_one_or_none():
            raise ConflictException("A user with this email address already exists")

        staff = User(
            email=data.email.lower(),
            hashed_password=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            role=data.role,
            status=UserStatus.ACTIVE,
            permissions=data.permissions,
            is_verified=True,
        )
        db.add(staff)
        await db.commit()
        await db.refresh(staff)
        return staff

    @classmethod
    async def authenticate(
        cls,
        db: AsyncSession,
        data: UserLoginRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """
        Authenticates user, creates active UserSession with hashed refresh token,
        and returns (User, access_token, refresh_token).
        """
        query = select(User).where(User.email == data.email.lower())
        result = await db.execute(query)
        user = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.hashed_password):
            raise UnauthorizedException("Invalid email or password")

        if user.status == UserStatus.BLOCKED:
            raise UnauthorizedException("This account is suspended or blocked")

        session_id = uuid.uuid4()
        refresh_token = create_refresh_token(user_id=user.id, session_id=session_id)
        access_token = create_access_token(
            user_id=user.id,
            role=user.role.value,
            permissions=user.permissions,
        )

        session = UserSession(
            id=session_id,
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            is_revoked=False,
        )
        db.add(session)
        await db.commit()

        return user, access_token, refresh_token

    @classmethod
    async def refresh_tokens(
        cls,
        db: AsyncSession,
        refresh_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """
        Rotates refresh token and detects reuse:
        If a revoked token is reused, all active sessions for that user are immediately terminated.
        """
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise UnauthorizedException("Invalid token type. Refresh token required.")

        user_id_str = payload.get("sub")
        session_id_str = payload.get("sid")
        if not user_id_str or not session_id_str:
            raise UnauthorizedException("Malformed refresh token payload")

        user_uuid = uuid.UUID(user_id_str)
        session_uuid = uuid.UUID(session_id_str)

        # Retrieve user
        user = (await db.execute(select(User).where(User.id == user_uuid))).scalar_one_or_none()
        if not user or user.status == UserStatus.BLOCKED:
            raise UnauthorizedException("User account is inactive or blocked")

        # Find session
        query = select(UserSession).where(UserSession.id == session_uuid)
        result = await db.execute(query)
        session = result.scalar_one_or_none()

        incoming_hash = hash_token(refresh_token)

        # REUSE DETECTION: If session not found, or token hash does not match, or already revoked
        if not session or session.is_revoked or session.token_hash != incoming_hash:
            # Immediate response to potential theft: Kill ALL active user sessions!
            await db.execute(
                update(UserSession)
                .where(UserSession.user_id == user_uuid)
                .values(is_revoked=True)
            )
            await db.commit()

            # Dispatch security alert notification
            await notification_service.send_security_alert(
                email=user.email,
                alert_message="A previously revoked or invalid refresh token was presented. All active sessions have been terminated for security.",
            )
            raise TokenReuseDetectedException()

        # Check expiration
        if session.expires_at < datetime.now(timezone.utc):
            session.is_revoked = True
            await db.commit()
            raise UnauthorizedException("Refresh token session has expired")

        # Invalidate current session (Rotation)
        session.is_revoked = True

        # Generate new session and token pair
        new_session_id = uuid.uuid4()
        new_refresh_token = create_refresh_token(user_id=user.id, session_id=new_session_id)
        new_access_token = create_access_token(
            user_id=user.id,
            role=user.role.value,
            permissions=user.permissions,
        )

        new_session = UserSession(
            id=new_session_id,
            user_id=user.id,
            token_hash=hash_token(new_refresh_token),
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            is_revoked=False,
        )
        db.add(new_session)
        await db.commit()

        return user, new_access_token, new_refresh_token

    @classmethod
    async def logout(cls, db: AsyncSession, refresh_token: Optional[str]) -> None:
        """
        Revokes the single session associated with the refresh token.
        """
        if not refresh_token:
            return
        try:
            payload = decode_token(refresh_token)
            session_id_str = payload.get("sid")
            if session_id_str:
                session_uuid = uuid.UUID(session_id_str)
                await db.execute(
                    update(UserSession)
                    .where(UserSession.id == session_uuid)
                    .values(is_revoked=True)
                )
                await db.commit()
        except Exception:
            pass

    @classmethod
    async def revoke_all_user_sessions(cls, db: AsyncSession, user_id: uuid.UUID) -> None:
        """
        Revokes all active sessions for a user (e.g., password reset or admin force logout).
        """
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(is_revoked=True)
        )
        await db.commit()


auth_service = AuthService()
