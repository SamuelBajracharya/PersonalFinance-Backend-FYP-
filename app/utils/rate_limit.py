from starlette.requests import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


def rate_limit_key_func(request: Request) -> str:
    """Use forwarded IP headers when present, else fall back to client host."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=rate_limit_key_func)
rate_limit_exceeded_handler = _rate_limit_exceeded_handler

__all__ = [
    "limiter",
    "RateLimitExceeded",
    "rate_limit_exceeded_handler",
    "rate_limit_key_func",
]
