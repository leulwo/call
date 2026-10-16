import logging
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from app.config import get_settings

logger = logging.getLogger(__name__)


def _create_limiter() -> Limiter:
    settings = get_settings()
    storage_uri = settings.redis_url if settings.redis_url else "memory://"
    try:
        return Limiter(
            key_func=get_remote_address,
            storage_uri=storage_uri,
        )
    except Exception as exc:
        logger.warning(f"Failed to initialize SlowAPI with {storage_uri} ({exc}); using in-memory limiter.")
        return Limiter(key_func=get_remote_address)


limiter = _create_limiter()


def limit(value: str):
    """Apply a slowapi rate limit, or no-op when the value is empty/'none'.

    Lets individual endpoints disable their limit via configuration without
    special-casing at the call site.
    """
    if not value or value.strip().lower() in {"none", "off", "disabled"}:
        def decorator(func):
            return func
        return decorator
    return limiter.limit(value)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Custom response when a user exceeds the API rate limit."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": f"Rate limit exceeded: {exc.detail}. Please slow down your requests.",
            "retry_after": getattr(exc, "retry_after", None),
        },
    )
