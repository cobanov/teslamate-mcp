"""Tests for the click CLI entry points (no live DB or network needed)."""

from __future__ import annotations

from click.testing import CliRunner

from teslamate_mcp import cli

_DUMMY_DB_URL = "postgresql://teslamate:secret@localhost:5432/teslamate"


def _invoke_http(monkeypatch, args: list[str]) -> tuple[object, dict]:
    """Run the `http` command with uvicorn stubbed out; capture the FastMCP instance."""
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
    """Regression: `http --json-response` crashed with ValueError on FastMCP settings.

    The old code assigned a nonexistent field (streamable_http_json_response) and
    did so after streamable_http_app() had already built the session manager.
    """
    result, captured = _invoke_http(monkeypatch, ["--json-response"])

    assert result.exit_code == 0, result.output
    assert captured["mcp"].settings.json_response is True
    assert captured["app"] is not None


def test_http_defaults_to_sse_response(monkeypatch):
    result, captured = _invoke_http(monkeypatch, [])

    assert result.exit_code == 0, result.output
    assert captured["mcp"].settings.json_response is False


def test_gen_token_prints_env_line():
    result = CliRunner().invoke(cli.main, ["gen-token"])

    assert result.exit_code == 0
    assert result.output.startswith("AUTH_TOKEN=")
    assert len(result.output.strip().removeprefix("AUTH_TOKEN=")) >= 32
