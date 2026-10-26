"""Authentication middleware for the HTTP transport.

Two credentials are accepted on /mcp routes, either one sufficient:

- `Authorization: Bearer <AUTH_TOKEN>` — the static token, compared timing-safe.
  This is what the Cloudflare MCP Server Portal sends upstream.
- `Cf-Access-Jwt-Assertion: <jwt>` — the signed assertion Cloudflare Access adds
  to every request it lets through. Verifying it (signature against the team's
  published keys, issuer, audience, expiry) lets MCP clients sign in through
  Access Managed OAuth and reach the server directly, without the portal —
  which rewrites `ui://` resource URIs and so breaks MCP Apps charts.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

CF_ACCESS_HEADER = "cf-access-jwt-assertion"

# Seconds between two requests for Cloudflare's key set, at the least.
_MIN_KEY_FETCH_INTERVAL = 30.0


class _SigningKeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class _ThrottledJWKClient(jwt.PyJWKClient):
    """A PyJWKClient that asks the endpoint for keys at most once per interval.

    PyJWKClient fetches the key set again whenever a token names a `kid` it
    does not know. The assertion header is read before anything is verified,
    so without a limit anyone could make the server call Cloudflare once per
    request by sending tokens with made-up key ids.

    Between fetches the last answer stands: a key Cloudflare has just rotated
    in is accepted up to one interval late, and after a failed fetch the keys
    stay unavailable until the interval has passed.
    """

    def __init__(
        self,
        uri: str,
        *,
        min_fetch_interval: float = _MIN_KEY_FETCH_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
        **kwargs: Any,
    ) -> None:
        super().__init__(uri, **kwargs)
        self._min_fetch_interval = min_fetch_interval
        self._clock = clock
        self._last_fetch: float | None = None
        self._last_data: Any = None
        # Held across the fetch, so requests that arrive together wait for one
        # answer and do not each start their own.
        self._fetch_lock = threading.Lock()

    def fetch_data(self) -> Any:
        with self._fetch_lock:
            now = self._clock()
            if self._last_fetch is not None and now - self._last_fetch < self._min_fetch_interval:
                if self._last_data is None:
                    raise jwt.PyJWKClientConnectionError(
                        "The last key fetch failed and it is too soon to try again"
                    )
                return self._last_data
            self._last_fetch = now
            self._last_data = None
            self._last_data = super().fetch_data()
            return self._last_data


class CloudflareAccessVerifier:
    """Verify Cloudflare Access application tokens (`Cf-Access-Jwt-Assertion`)."""

    def __init__(
        self,
        *,
        team_domain: str,
        audience: str,
        jwks_client: _SigningKeySource | None = None,
    ) -> None:
        host = team_domain.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
        self.issuer = f"https://{host}"
        self.audience = audience.strip()
        # The client caches the key set and refetches on an unknown `kid`, so
        # Cloudflare's periodic key rotation is picked up without a restart.
        # The short timeout bounds how long requests wait behind one fetch.
        self._keys = jwks_client or _ThrottledJWKClient(
            f"{self.issuer}/cdn-cgi/access/certs", cache_keys=True, lifespan=3600, timeout=10
        )

    def verify(self, token: str) -> bool:
        """Return True only for a correctly signed, unexpired token for this app."""
        try:
            key = self._keys.get_signing_key_from_jwt(token)
            jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except jwt.PyJWKClientError as exc:
            logger.warning("Cloudflare Access keys unavailable: %s", exc)
            return False
        except jwt.PyJWTError as exc:
            logger.info("Rejected Cloudflare Access assertion: %s", exc)
            return False
        return True


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Require AUTH_TOKEN or a verified Cloudflare Access assertion on /mcp routes."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        auth_token: str = "",
        access_verifier: CloudflareAccessVerifier | None = None,
        protected_prefix: str = "/mcp",
    ) -> None:
        super().__init__(app)
        if not auth_token and access_verifier is None:
            raise ValueError("BearerAuthMiddleware needs an auth_token or an access_verifier")
        self._expected = auth_token.encode("utf-8")
        self._access = access_verifier
        self._protected_prefix = protected_prefix

    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith(self._protected_prefix):
            return await call_next(request)

        assertion = request.headers.get(CF_ACCESS_HEADER)
        # Key fetches are blocking HTTP on a cache miss; keep them off the loop.
        if (
            assertion
            and self._access is not None
            and await asyncio.to_thread(self._access.verify, assertion)
        ):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return self._unauthorized("Authorization required")

        # With only Access configured there is no static token to match — an
        # empty expected value must never compare equal to "Bearer ".
        provided = header.split(" ", 1)[1].encode("utf-8")
        if not self._expected or not hmac.compare_digest(provided, self._expected):
            return self._unauthorized("Invalid token")

        return await call_next(request)

    @staticmethod
    def _unauthorized(message: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": message},
            headers={"WWW-Authenticate": "Bearer"},
        )
