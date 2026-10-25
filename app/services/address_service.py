import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.address import Address


async def list_addresses(session: AsyncSession, user_id: uuid.UUID) -> list[Address]:
    stmt = select(Address).where(Address.user_id == user_id, Address.deleted_at.is_(None)).order_by(Address.is_default.desc(), Address.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def get_address(session: AsyncSession, user_id: uuid.UUID, addr_id: uuid.UUID) -> Address | None:
    stmt = select(Address).where(Address.id == addr_id, Address.user_id == user_id, Address.deleted_at.is_(None))
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_address(session: AsyncSession, user_id: uuid.UUID, data: dict) -> tuple[Address | None, str | None]:
    active = await list_addresses(session, user_id)
    if len(active) >= 10:
        return None, "Maximum 10 active addresses allowed"
    is_def = data.get("is_default", False) or len(active) == 0
    if is_def:
        await session.execute(update(Address).where(Address.user_id == user_id).values(is_default=False))
    addr = Address(user_id=user_id, **{**data, "is_default": is_def})
    session.add(addr)
    await session.flush()
    return addr, None


async def update_address(session: AsyncSession, addr: Address, data: dict) -> Address:
    if data.get("is_default"):
        await session.execute(update(Address).where(Address.user_id == addr.user_id).values(is_default=False))
    for k, v in data.items():
        if v is not None:
            setattr(addr, k, v)
    await session.flush()
    return addr


async def delete_address(session: AsyncSession, addr: Address) -> None:
    addr.deleted_at = datetime.now(timezone.utc)
    addr.is_default = False
    await session.flush()


async def set_default_address(session: AsyncSession, addr: Address) -> Address:
    await session.execute(update(Address).where(Address.user_id == addr.user_id).values(is_default=False))
    addr.is_default = True
    await session.flush()
    return addr
