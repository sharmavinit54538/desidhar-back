from contextlib import asynccontextmanager
from typing import AsyncGenerator
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.api.deps import get_db
from app.core.rate_limit import limiter
from app.main import app

settings = get_settings()

db_test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
db_test_session_maker = async_sessionmaker(db_test_engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
    async with db_test_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with override_get_session() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset the rate limiter between tests to avoid cross-test throttling."""
    limiter.reset()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with db_test_session_maker() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
