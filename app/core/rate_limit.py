from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings

# Global limiter instance initialized with client remote IP address
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.DEFAULT_RATE_LIMIT],
    headers_enabled=True,
    storage_uri=settings.REDIS_URL,
)
