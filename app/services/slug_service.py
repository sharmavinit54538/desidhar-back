import re
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession


async def generate_unique_slug(session: AsyncSession, table, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug = base
    suffix = 1
    while True:
        result = await session.execute(select(func.count()).where(table.slug == slug))
        if result.scalar() == 0:
            return slug
        suffix += 1
        slug = f"{base}-{suffix}"

