import asyncio
import getpass
import sys
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.db import engine, async_session_maker, Base
from app.core.passwords import hash_password
from app.models.user import User, Role


async def create_admin(username: str) -> None:
    settings = get_settings()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.username == username.lower(), User.role == Role.admin))
        if result.scalar_one_or_none():
            print(f"Admin '{username}' already exists")
            return

        while True:
            password = getpass.getpass("Enter password (min 12 chars): ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("Passwords do not match")
                continue
            if len(password) < 12:
                print("Password must be at least 12 characters")
                continue
            break

        password_hash = hash_password(password)
        admin_user = User(
            id=uuid.uuid4(),
            role=Role.admin,
            username=username.lower(),
            password_hash=password_hash,
        )
        session.add(admin_user)
        await session.commit()
        print(f"Admin '{username}' created successfully")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.create_admin <username>")
        sys.exit(1)

    asyncio.run(create_admin(sys.argv[1]))
