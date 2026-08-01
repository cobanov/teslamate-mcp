"""Tests for BearerAuthMiddleware (HTTP bearer-token auth on /mcp routes)."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from teslamate_mcp.auth import BearerAuthMiddleware

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
