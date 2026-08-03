"""Tests for the click CLI entry points. Only the live-database health test needs Docker."""

from __future__ import annotations

import json
from types import SimpleNamespace

from click.testing import CliRunner
from starlette.testclient import TestClient

from teslamate_mcp import cli

_DUMMY_DB_URL = "postgresql://teslamate:secret@localhost:5432/teslamate"


def _invoke_http(monkeypatch, args: list[str]) -> tuple[object, dict]:
    """Run the `http` command with uvicorn stubbed out; capture the MCPServer instance."""
    captured: dict = {}

    real_create_server = cli.create_server

    def capture_server(settings):
        mcp = real_create_server(settings)
        captured["mcp"] = mcp
        return mcp

    def fake_run(app, **kwargs):
        captured["app"] = app

    monkeypatch.setattr(cli, "create_server", capture_server)
    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.setenv("DATABASE_URL", _DUMMY_DB_URL)

    result = CliRunner().invoke(cli.main, ["http", *args])
    return result, captured


def test_http_json_response_flag_starts_cleanly(monkeypatch):
    """Regression: `http --json-response` once crashed before reaching the
    session manager. Under SDK v2 the flag is a streamable_http_app() kwarg;
    assert it actually lands on the built session manager."""
    result, captured = _invoke_http(monkeypatch, ["--json-response"])

    assert result.exit_code == 0, result.output
    assert captured["mcp"].session_manager.json_response is True
    assert captured["app"] is not None


def test_http_defaults_to_sse_response(monkeypatch):
    result, captured = _invoke_http(monkeypatch, [])

    assert result.exit_code == 0, result.output
    assert captured["mcp"].session_manager.json_response is False
    assert captured["mcp"].session_manager.stateless is False


def test_http_stateless_flag_reaches_session_manager(monkeypatch):
    result, captured = _invoke_http(monkeypatch, ["--stateless"])

    assert result.exit_code == 0, result.output
    assert captured["mcp"].session_manager.stateless is True


async def test_mcp_trailing_slash_is_normalized_not_redirected(monkeypatch):
    """Regression: the Cloudflare portal's saved hostname ends in /mcp/ (the
    SDK v1 canonical form) and cannot be edited; SDK v2 routes at /mcp and
    307-redirects /mcp/, which the portal rejects (Cloudflare error 1003)."""
    seen: dict = {}

    async def downstream(scope, receive, send):
        seen["path"] = scope["path"]
        seen["raw_path"] = scope["raw_path"]

    mw = cli.NormalizeMcpPathMiddleware(downstream)
    await mw({"type": "http", "path": "/mcp/", "raw_path": b"/mcp/"}, None, None)
    assert seen == {"path": "/mcp", "raw_path": b"/mcp"}

    await mw({"type": "http", "path": "/health", "raw_path": b"/health"}, None, None)
    assert seen["path"] == "/health"  # untouched

    _, captured = _invoke_http(monkeypatch, ["--json-response"])
    stack = [m.cls.__name__ for m in captured["app"].user_middleware]
    assert "NormalizeMcpPathMiddleware" in stack


def test_gen_token_prints_env_line():
    result = CliRunner().invoke(cli.main, ["gen-token"])

    assert result.exit_code == 0
    assert result.output.startswith("AUTH_TOKEN=")
    assert len(result.output.strip().removeprefix("AUTH_TOKEN=")) >= 32


def test_health_reports_degraded_when_the_database_is_unavailable(monkeypatch):
    """Regression: /health answered `ok` while every MCP call failed with a 500.

    The probe backs the Dockerfile HEALTHCHECK, so a liveness-only answer made
    a container that could not reach PostgreSQL look healthy indefinitely.
    """
    _, captured = _invoke_http(monkeypatch, [])
    # No lifespan is entered here, so the pool is closed — the same state a
    # container is in when PostgreSQL is unreachable.
    response = TestClient(captured["app"]).get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] in {"unavailable", "unreachable"}


async def test_health_reports_ok_against_a_live_database(pool):
    handler = cli._make_health(SimpleNamespace(teslamate_app_context=SimpleNamespace(pool=pool)))

    response = await handler(SimpleNamespace())

    assert response.status_code == 200
    assert json.loads(response.body)["database"] == "ok"


async def test_health_survives_an_exception_with_no_message():
    """Regression: an empty str(exc) has no lines, and indexing it 500'd the probe.

    `asyncio.timeout` raises a bare TimeoutError that stringifies to "", so a
    database slow enough to trip the probe's own 3s cap — precisely the case
    the probe exists for — took this path.
    """

    class _Pool:
        closed = False

        def connection(self):
            raise TimeoutError()

    handler = cli._make_health(SimpleNamespace(teslamate_app_context=SimpleNamespace(pool=_Pool())))

    response = await handler(SimpleNamespace())

    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["status"] == "degraded"
    assert body["detail"] == "TimeoutError"
