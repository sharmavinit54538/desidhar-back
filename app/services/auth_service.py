from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.passwords import hash_password, verify_password, dummy_hash
from app.core.tokens import create_customer_token, create_admin_token
from app.models.user import User, Role


async def get_or_create_customer(session: AsyncSession, email: str) -> User:
    email_lower = email.lower().strip()
    result = await session.execute(select(User).where(User.email == email_lower))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(role=Role.customer, email=email_lower)
        session.add(user)
        await session.flush()
    return user


async def authenticate_admin(session: AsyncSession, username: str, password: str) -> User | None:
    username_lower = username.lower().strip()
    result = await session.execute(select(User).where(User.username == username_lower, User.role == Role.admin))
    user = result.scalar_one_or_none()

    if user is None:
        verify_password(password, dummy_hash())
        return None

    if user.locked_until and user.locked_until > user.locked_until.replace(tzinfo=None):
        return None

    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= 5:
            from app.core.clock import utc_now
            from datetime import timedelta
            user.locked_until = utc_now() + timedelta(minutes=15)
        return None

    user.failed_logins = 0
    user.locked_until = None
    return user


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    import uuid
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return None
    result = await session.execute(select(User).where(User.id == uid, User.is_active.is_(True)))
    return result.scalar_one_or_none()