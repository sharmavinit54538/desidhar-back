import uuid
from typing import List, Optional
from fastapi import Request, Depends, Cookie, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_token
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.models.user import User, UserRole, UserStatus


def extract_token_from_request(
    request: Request,
    access_token_cookie: Optional[str] = Cookie(None, alias="access_token"),
    authorization_header: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """
    Extracts the JWT access token from HTTP-Only cookie or Bearer Authorization header.
    """
    if access_token_cookie:
        return access_token_cookie
    if authorization_header and authorization_header.startswith("Bearer "):
        return authorization_header[7:].strip()
    raise UnauthorizedException("Authentication token missing")


async def get_current_user(
    token: str = Depends(extract_token_from_request),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validates the access token, verifies user existence and ACTIVE status.
    """
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise UnauthorizedException("Invalid token type. Access token required.")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise UnauthorizedException("Token payload missing subject")

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise UnauthorizedException("Invalid subject identifier in token")

    query = select(User).where(User.id == user_uuid)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException("User associated with this token no longer exists")

    if user.status == UserStatus.BLOCKED:
        raise ForbiddenException(
            message="Your account has been suspended or blocked. Please contact customer support.",
            error_code="ACCOUNT_BLOCKED",
        )

    return user


async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Optional user dependency. Returns None for guests without raising UnauthorizedException.
    """
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        return None

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_uuid = uuid.UUID(payload.get("sub"))
        query = select(User).where(User.id == user_uuid)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if user and user.status == UserStatus.ACTIVE:
            return user
        return None
    except Exception:
        return None


def get_guest_session_id(
    request: Request,
    guest_session_id_cookie: Optional[str] = Cookie(None, alias="guest_session_id"),
    x_guest_session_id_header: Optional[str] = Header(None, alias="X-Guest-Session-Id"),
) -> Optional[str]:
    return guest_session_id_cookie or x_guest_session_id_header


class RoleChecker:
    """
    Enforces that the authenticated user possesses one of the allowed roles.
    Returns 403 Forbidden on role mismatch.
    """
    def __init__(self, allowed_roles: List[UserRole]):
        self.allowed_roles = allowed_roles

    async def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            role_names = ", ".join([r.value for r in self.allowed_roles])
            raise ForbiddenException(
                message=f"Access forbidden: Requires one of [{role_names}] roles",
                error_code="INSUFFICIENT_ROLE",
            )
        return current_user


class PermissionChecker:
    """
    Enforces granular permissions.
    SUPER_ADMIN bypasses all permission checks automatically.
    """
    def __init__(self, required_permissions: List[str]):
        self.required_permissions = required_permissions

    async def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        # SUPER_ADMIN has god-mode privileges
        if current_user.role == UserRole.SUPER_ADMIN:
            return current_user

        user_perms = set(current_user.permissions or [])
        missing = [p for p in self.required_permissions if p not in user_perms]

        if missing:
            raise ForbiddenException(
                message=f"Access forbidden: Missing required permission(s): {', '.join(missing)}",
                error_code="INSUFFICIENT_PERMISSIONS",
                details=[{"missing_permissions": missing}],
            )
        return current_user
