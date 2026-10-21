from typing import Optional, Dict, Any
import json
import logging
import redis.asyncio as aioredis
from redis.asyncio import Redis
from app.core.config import settings

logger = logging.getLogger("desidhar.redis")

_redis_client: Optional[Redis] = None


async def init_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
            # Ping test
            await _redis_client.ping()
            logger.info("Successfully connected to Redis.")
        except Exception as e:
            logger.warning(f"Redis connection failed ({e}). Running in fallback mode.")
            _redis_client = None
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("Closed Redis connection.")


def get_redis() -> Optional[Redis]:
    return _redis_client


class RedisCartCache:
    """
    Manages guest cart operations stored in Redis.
    Key format: 'guest_cart:{session_id}'
    Value: JSON dict of {product_id_str: quantity}
    """

    @staticmethod
    def _key(session_id: str) -> str:
        return f"guest_cart:{session_id}"

    @classmethod
    async def get_cart(cls, session_id: str) -> Dict[str, int]:
        client = get_redis()
        if not client:
            return {}
        try:
            raw = await client.get(cls._key(session_id))
            if raw:
                return json.loads(raw)
            return {}
        except Exception as e:
            logger.error(f"Error fetching guest cart from Redis: {e}")
            return {}

    @classmethod
    async def save_cart(cls, session_id: str, items: Dict[str, int]) -> None:
        client = get_redis()
        if not client:
            return
        try:
            key = cls._key(session_id)
            if not items:
                await client.delete(key)
            else:
                await client.set(
                    key,
                    json.dumps(items),
                    ex=settings.REDIS_GUEST_CART_TTL_SECONDS,
                )
        except Exception as e:
            logger.error(f"Error saving guest cart to Redis: {e}")

    @classmethod
    async def delete_cart(cls, session_id: str) -> None:
        client = get_redis()
        if not client:
            return
        try:
            await client.delete(cls._key(session_id))
        except Exception as e:
            logger.error(f"Error deleting guest cart from Redis: {e}")
