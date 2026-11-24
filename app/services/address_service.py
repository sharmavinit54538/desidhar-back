import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.address import Address
from app.models.user import User


async def _lock_address_book(session: AsyncSession, user_id: uuid.UUID) -> None:
    # Lock a row that exists even when the user has no addresses yet. This keeps
    # concurrent mutations within the address limit and the single-default rule.
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())


async def _clear_defaults(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(Address)
        .where(Address.user_id == user_id, Address.deleted_at.is_(None), Address.is_default.is_(True))
        .values(is_default=False)
    )


async def list_addresses(session: AsyncSession, user_id: uuid.UUID) -> list[Address]:
    stmt = select(Address).where(Address.user_id == user_id, Address.deleted_at.is_(None)).order_by(Address.is_default.desc(), Address.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def get_address(session: AsyncSession, user_id: uuid.UUID, addr_id: uuid.UUID) -> Address | None:
    # Mutation routes use this lookup before changing an address. Keep the lock
    # until their transaction commits so a concurrent deletion cannot race it.
    await _lock_address_book(session, user_id)
    stmt = (
        select(Address)
        .where(Address.id == addr_id, Address.user_id == user_id, Address.deleted_at.is_(None))
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_address(session: AsyncSession, user_id: uuid.UUID, data: dict) -> tuple[Address | None, str | None]:
    await _lock_address_book(session, user_id)
    active = await list_addresses(session, user_id)
    if len(active) >= 10:
        return None, "Maximum 10 active addresses allowed"
    is_def = data.get("is_default", False) or not any(addr.is_default for addr in active)
    if is_def:
        await _clear_defaults(session, user_id)
    addr = Address(user_id=user_id, **{**data, "is_default": is_def})
    session.add(addr)
    await session.flush()
    return addr, None


async def update_address(session: AsyncSession, addr: Address, data: dict) -> Address:
    if data.get("is_default"):
        await _clear_defaults(session, addr.user_id)
        addr.is_default = True
    for k, v in data.items():
        # Explicit null clears nullable address fields. An unchecked default
        # checkbox keeps the existing default; select another address to move it.
        if k != "is_default":
            setattr(addr, k, v)
    await session.flush()
    return addr


async def delete_address(session: AsyncSession, addr: Address) -> None:
    addr.deleted_at = datetime.now(timezone.utc)
    addr.is_default = False
    # Remove the old default from the partial unique index before promoting one.
    await session.flush()
    active = await list_addresses(session, addr.user_id)
    if active and not any(address.is_default for address in active):
        active[0].is_default = True
        await session.flush()


async def set_default_address(session: AsyncSession, addr: Address) -> Address:
    await _clear_defaults(session, addr.user_id)
    addr.is_default = True
    await session.flush()
    return addr

