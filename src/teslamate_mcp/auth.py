"""Bearer-token authentication middleware for the HTTP transport."""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Validate `Authorization: Bearer <token>` on /mcp routes using a timing-safe compare."""

    def __init__(self, app: ASGIApp, *, auth_token: str, protected_prefix: str = "/mcp") -> None:
        super().__init__(app)
        self._expected = auth_token.encode("utf-8")
        self._protected_prefix = protected_prefix

    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith(self._protected_prefix):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return self._unauthorized("Authorization required")

        provided = header.split(" ", 1)[1].encode("utf-8")
        if not hmac.compare_digest(provided, self._expected):
            return self._unauthorized("Invalid token")

        return await call_next(request)

    @staticmethod
    def _unauthorized(message: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": message},
            headers={"WWW-Authenticate": "Bearer"},
        )
