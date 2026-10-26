import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import get_session
from app.services.payment_method_service import seed_payment_methods



async def main():
    async with get_session() as session:
        await seed_payment_methods(session)
        await session.commit()
    print("Payment methods seeded successfully.")


if __name__ == "__main__":
    asyncio.run(main())
