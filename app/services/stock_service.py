import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def reserve_stock(session: AsyncSession, items: list[tuple[uuid.UUID, int]]) -> tuple[bool, str | None]:
    reserved: list[tuple[uuid.UUID, int]] = []
    for prod_id, qty in items:
        stmt = text("UPDATE products SET stock_qty = stock_qty - :q WHERE id = :id AND stock_qty >= :q RETURNING id")
        res = await session.execute(stmt, {"id": prod_id, "q": qty})
        if not res.fetchone():
            for r_id, r_qty in reserved:
                await session.execute(text("UPDATE products SET stock_qty = stock_qty + :q WHERE id = :id"), {"id": r_id, "q": r_qty})
            return False, f"Insufficient stock for product {prod_id}"
        reserved.append((prod_id, qty))
    return True, None


async def release_stock(session: AsyncSession, items: list[tuple[uuid.UUID, int]]) -> None:
    for prod_id, qty in items:
        await session.execute(text("UPDATE products SET stock_qty = stock_qty + :q WHERE id = :id"), {"id": prod_id, "q": qty})
    await session.flush()
