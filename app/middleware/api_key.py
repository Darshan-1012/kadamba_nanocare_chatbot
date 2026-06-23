"""API Key authentication middleware.

Validates the ``X-API-Key`` header on every request except public paths
(health check, docs, root). When ``NANOCARE_API_KEY`` is not set in ``.env``,
the middleware is **bypassed** so local development works without friction.

Usage in .env::

    NANOCARE_API_KEY=your-secret-key-here

Clients must then send::

    X-API-Key: your-secret-key-here
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import API_KEY

log = logging.getLogger(__name__)

# Paths that never require an API key
PUBLIC_PATHS = frozenset({
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/health",
    "/api/v1/wellness/health",
})


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests without a valid ``X-API-Key`` header.

    If ``NANOCARE_API_KEY`` is empty/unset, all requests are allowed
    (development mode).
    """

    async def dispatch(self, request: Request, call_next):
        # Skip if no API key is configured (dev mode)
        if not API_KEY:
            return await call_next(request)

        # Skip public paths
        path = request.url.path.rstrip("/") or "/"
        if path in PUBLIC_PATHS:
            return await call_next(request)

        # Skip static file serving (frontend demos)
        if path.startswith("/static") or path.startswith("/api/frontend"):
            return await call_next(request)

        # Validate
        provided_key = request.headers.get("X-API-Key", "")
        if provided_key != API_KEY:
            log.warning(f"API key rejected for {request.method} {path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)
