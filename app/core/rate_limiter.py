from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

# In-memory limiter by default. For multi-instance deployments, swap
# storage_uri to a Redis URI, e.g. "redis://localhost:6379/1".
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
)