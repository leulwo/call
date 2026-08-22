"""ExamPaper Refine - SlowAPI Rate Limiter Configuration."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, Response
from fastapi.responses import JSONResponse

# Create global limiter keyed by remote IP address
limiter = Limiter(key_func=get_remote_address)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Custom response when a user exceeds the API rate limit."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": f"Rate limit exceeded: {exc.detail}. Please slow down your requests.",
            "retry_after": getattr(exc, "retry_after", None),
        },
    )
