"""Tests for BearerAuthMiddleware (bearer token and Cloudflare Access auth on /mcp routes)."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from teslamate_mcp.auth import BearerAuthMiddleware, CloudflareAccessVerifier
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


def _assertion(*, key=_KEY, aud=_AUD, iss=_ISSUER, exp_offset=300) -> str:
    now = int(time.time())
    claims = {"aud": [aud], "iss": iss, "iat": now, "exp": now + exp_offset, "email": "me@x"}
    return jwt.encode(claims, key, algorithm="RS256")


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
