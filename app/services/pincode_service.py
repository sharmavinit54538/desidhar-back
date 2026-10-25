import uuid
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pincode import Pincode


async def get_pincode_by_id(session: AsyncSession, pincode_id: uuid.UUID) -> Pincode | None:
    result = await session.execute(select(Pincode).where(Pincode.id == pincode_id))
    return result.scalar_one_or_none()


async def get_pincode_by_code(session: AsyncSession, code: str) -> Pincode | None:
    result = await session.execute(select(Pincode).where(Pincode.pincode == code.strip()))
    return result.scalar_one_or_none()


async def list_pincodes(
    session: AsyncSession,
    q: str | None = None,
    city: str | None = None,
    state: str | None = None,
    is_serviceable: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Pincode], int]:
    stmt = select(Pincode)
    count_stmt = select(func.count()).select_from(Pincode)
    if q:
        pattern = f"%{q.strip()}%"
        flt = or_(Pincode.pincode.ilike(pattern), Pincode.area_name.ilike(pattern), Pincode.city.ilike(pattern))
        stmt = stmt.where(flt)
        count_stmt = count_stmt.where(flt)
    if city:
        stmt = stmt.where(Pincode.city.ilike(f"%{city.strip()}%"))
        count_stmt = count_stmt.where(Pincode.city.ilike(f"%{city.strip()}%"))
    if state:
        stmt = stmt.where(Pincode.state.ilike(f"%{state.strip()}%"))
        count_stmt = count_stmt.where(Pincode.state.ilike(f"%{state.strip()}%"))
    if is_serviceable is not None:
        stmt = stmt.where(Pincode.is_serviceable.is_(is_serviceable))
        count_stmt = count_stmt.where(Pincode.is_serviceable.is_(is_serviceable))

    total = (await session.execute(count_stmt)).scalar() or 0
    stmt = stmt.order_by(Pincode.pincode.asc()).offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(stmt)
    return list(result.scalars().all()), total


async def create_pincode(session: AsyncSession, data: dict) -> Pincode:
    pincode = Pincode(**data)
    session.add(pincode)
    await session.flush()
    return pincode


async def update_pincode(session: AsyncSession, pincode: Pincode, data: dict) -> Pincode:
    for key, value in data.items():
        if value is not None:
            setattr(pincode, key, value)
    await session.flush()
    return pincode


async def delete_pincode(session: AsyncSession, pincode: Pincode) -> None:
    await session.delete(pincode)
    await session.flush()
