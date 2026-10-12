"""Tests for BearerAuthMiddleware (bearer token and Cloudflare Access auth on /mcp routes)."""

from __future__ import annotations

import io
import json
import time
from urllib.error import URLError

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from teslamate_mcp.auth import (
    BearerAuthMiddleware,
    CloudflareAccessVerifier,
    _ThrottledJWKClient,
)
from teslamate_mcp.config import Settings

_TOKEN = "sekrit-token"


@pytest.fixture
def client() -> TestClient:
    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(
        routes=[
            Route("/mcp", ok, methods=["GET", "POST"]),
            Route("/mcp/", ok, methods=["GET", "POST"]),
            Route("/health", ok),
        ]
    )
    app.add_middleware(BearerAuthMiddleware, auth_token=_TOKEN)
    return TestClient(app)


def test_missing_header_is_rejected(client) -> None:
    response = client.get("/mcp")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"error": "Authorization required"}


def test_non_bearer_scheme_is_rejected(client) -> None:
    response = client.get("/mcp", headers={"Authorization": f"Basic {_TOKEN}"})
    assert response.status_code == 401
    assert response.json() == {"error": "Authorization required"}


def test_wrong_token_is_rejected(client) -> None:
    response = client.get("/mcp", headers={"Authorization": "Bearer not-the-token"})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"error": "Invalid token"}


def test_correct_token_passes(client) -> None:
    response = client.get("/mcp", headers={"Authorization": f"Bearer {_TOKEN}"})
    assert response.status_code == 200
    assert response.text == "ok"


def test_bearer_scheme_is_case_insensitive(client) -> None:
    response = client.get("/mcp", headers={"Authorization": f"BEARER {_TOKEN}"})
    assert response.status_code == 200


def test_trailing_slash_path_is_still_protected(client) -> None:
    assert client.get("/mcp/").status_code == 401
    assert client.get("/mcp/", headers={"Authorization": f"Bearer {_TOKEN}"}).status_code == 200


def test_paths_outside_prefix_are_exempt(client) -> None:
    # /health is how the Docker HEALTHCHECK stays unauthenticated.
    assert client.get("/health").status_code == 200


# --- Cloudflare Access assertions (Cf-Access-Jwt-Assertion) -----------------

_TEAM = "myteam.cloudflareaccess.com"
_ISSUER = f"https://{_TEAM}"
_AUD = "aud-tag-123"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StaticKeys:
    """Stands in for PyJWKClient: always resolves to one public key."""

    def __init__(self, private_key) -> None:
        self._public = private_key.public_key()

    def get_signing_key_from_jwt(self, token: str):
        return jwt.PyJWK.from_dict(jwt.algorithms.RSAAlgorithm.to_jwk(self._public, as_dict=True))


class _UnreachableKeys:
    def get_signing_key_from_jwt(self, token: str):
        raise jwt.PyJWKClientError("Fail to fetch data from the url")


def _assertion(*, key=_KEY, aud=_AUD, iss=_ISSUER, exp_offset=300, kid=None) -> str:
    now = int(time.time())
    claims = {"aud": [aud], "iss": iss, "iat": now, "exp": now + exp_offset, "email": "me@x"}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid} if kid else None)


def _access_client(*, auth_token: str = "", keys=None) -> TestClient:
    async def ok(request):
        return PlainTextResponse("ok")

    verifier = CloudflareAccessVerifier(
        team_domain=_TEAM, audience=_AUD, jwks_client=keys or _StaticKeys(_KEY)
    )
    app = Starlette(routes=[Route("/mcp", ok, methods=["GET", "POST"]), Route("/health", ok)])
    app.add_middleware(BearerAuthMiddleware, auth_token=auth_token, access_verifier=verifier)
    return TestClient(app)


def test_valid_access_assertion_passes() -> None:
    response = _access_client().get("/mcp", headers={"Cf-Access-Jwt-Assertion": _assertion()})
    assert response.status_code == 200


def test_access_assertion_passes_despite_foreign_bearer() -> None:
    # Managed OAuth clients send Access's opaque token as Authorization; the
    # assertion Access adds alongside it is what authenticates the request.
    headers = {"Cf-Access-Jwt-Assertion": _assertion(), "Authorization": "Bearer oauth:opaque"}
    assert _access_client(auth_token=_TOKEN).get("/mcp", headers=headers).status_code == 200


@pytest.mark.parametrize(
    "token",
    [
        _assertion(aud="some-other-app"),
        _assertion(iss="https://evil.cloudflareaccess.com"),
        _assertion(exp_offset=-60),
        _assertion(key=_OTHER_KEY),
        "not-a-jwt",
    ],
    ids=["wrong-aud", "wrong-iss", "expired", "wrong-key", "garbage"],
)
def test_bad_access_assertions_are_rejected(token: str) -> None:
    response = _access_client().get("/mcp", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 401


def test_unreachable_access_keys_fail_closed() -> None:
    client = _access_client(keys=_UnreachableKeys())
    assert client.get("/mcp", headers={"Cf-Access-Jwt-Assertion": _assertion()}).status_code == 401


def test_access_only_rejects_empty_bearer() -> None:
    # No AUTH_TOKEN configured: "Bearer " must not match the empty expected token.
    client = _access_client()
    assert client.get("/mcp", headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get("/mcp").status_code == 401


def test_static_token_still_works_alongside_access() -> None:
    client = _access_client(auth_token=_TOKEN)
    assert client.get("/mcp", headers={"Authorization": f"Bearer {_TOKEN}"}).status_code == 200


def test_middleware_requires_some_credential() -> None:
    with pytest.raises(ValueError):
        BearerAuthMiddleware(Starlette())


def test_team_domain_accepts_url_form() -> None:
    verifier = CloudflareAccessVerifier(
        team_domain="https://myteam.cloudflareaccess.com/",
        audience=_AUD,
        jwks_client=_StaticKeys(_KEY),
    )
    assert verifier.issuer == _ISSUER


def test_cf_access_settings_must_come_in_pairs() -> None:
    with pytest.raises(ValueError):
        Settings(database_url="postgresql://x", cf_access_team_domain=_TEAM)
    with pytest.raises(ValueError):
        Settings(database_url="postgresql://x", cf_access_aud=_AUD)
    Settings(database_url="postgresql://x", cf_access_team_domain=_TEAM, cf_access_aud=_AUD)


# --- Fetching Cloudflare's keys ----------------------------------------------


class _KeyEndpoint:
    """Stands in for /cdn-cgi/access/certs and counts how often it is asked."""

    def __init__(self, **keys) -> None:
        self.keys = keys
        self.fetches = 0
        self.down = False

    def __call__(self, request, timeout=None, context=None):
        self.fetches += 1
        if self.down:
            raise URLError("unreachable")
        jwks = [
            {**jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": kid}
            for kid, key in self.keys.items()
        ]
        return io.BytesIO(json.dumps({"keys": jwks}).encode())


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def key_endpoint(monkeypatch) -> _KeyEndpoint:
    endpoint = _KeyEndpoint(current=_KEY)
    monkeypatch.setattr("urllib.request.urlopen", endpoint)
    return endpoint


def _throttled_verifier(clock: _Clock) -> CloudflareAccessVerifier:
    keys = _ThrottledJWKClient(
        f"{_ISSUER}/cdn-cgi/access/certs", min_fetch_interval=30, clock=clock, cache_keys=True
    )
    return CloudflareAccessVerifier(team_domain=_TEAM, audience=_AUD, jwks_client=keys)


def test_unknown_key_ids_do_not_refetch_the_key_set(key_endpoint) -> None:
    clock = _Clock()
    verifier = _throttled_verifier(clock)
    assert verifier.verify(_assertion(kid="current"))
    assert key_endpoint.fetches == 1

    # Anyone can send these: each names a key id the server has never seen.
    for n in range(20):
        assert not verifier.verify(_assertion(key=_OTHER_KEY, kid=f"made-up-{n}"))
    assert key_endpoint.fetches == 1

    clock.now += 31
    for n in range(20):
        assert not verifier.verify(_assertion(key=_OTHER_KEY, kid=f"later-{n}"))
    assert key_endpoint.fetches == 2
    assert verifier.verify(_assertion(kid="current"))


def test_rotated_key_is_accepted_once_the_interval_has_passed(key_endpoint) -> None:
    clock = _Clock()
    verifier = _throttled_verifier(clock)
    assert verifier.verify(_assertion(kid="current"))

    key_endpoint.keys["rotated"] = _OTHER_KEY
    rotated = _assertion(key=_OTHER_KEY, kid="rotated")
    assert not verifier.verify(rotated)

    clock.now += 31
    assert verifier.verify(rotated)
    assert key_endpoint.fetches == 2


def test_failed_key_fetch_is_not_repeated_at_once(key_endpoint) -> None:
    clock = _Clock()
    verifier = _throttled_verifier(clock)
    key_endpoint.down = True
    assert not verifier.verify(_assertion(kid="current"))
    assert not verifier.verify(_assertion(kid="current"))
    assert key_endpoint.fetches == 1

    key_endpoint.down = False
    assert not verifier.verify(_assertion(kid="current"))
    clock.now += 31
    assert verifier.verify(_assertion(kid="current"))
    assert key_endpoint.fetches == 2


def test_verifier_throttles_key_fetches_by_default() -> None:
    verifier = CloudflareAccessVerifier(team_domain=_TEAM, audience=_AUD)
    assert isinstance(verifier._keys, _ThrottledJWKClient)
