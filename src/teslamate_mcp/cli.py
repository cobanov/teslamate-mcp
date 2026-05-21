"""Command-line entry point for the TeslaMate MCP server."""

from __future__ import annotations

import logging
import secrets
import sys

import click
import uvicorn
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import __version__
from .auth import BearerAuthMiddleware
from .config import load_settings
from .server import create_server
from .tools import discover_predefined_tools


async def _health(_request: Request) -> JSONResponse:
    """Liveness probe used by Docker HEALTHCHECK and any external monitor."""
    return JSONResponse({"status": "ok", "version": __version__})


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="teslamate-mcp")
def main() -> None:
    """TeslaMate MCP server — query your Tesla data from any MCP-aware client."""


@main.command()
def stdio() -> None:
    """Run the MCP server over stdio (for local clients like Cursor or Claude Desktop)."""
    settings = load_settings()
    _configure_logging(settings.log_level)
    mcp = create_server(settings)
    mcp.run(transport="stdio")


@main.command()
@click.option("--host", default=None, help="HTTP bind host (overrides config).")
@click.option("--port", default=None, type=int, help="HTTP bind port (overrides config).")
@click.option(
    "--auth-token",
    default=None,
    envvar="AUTH_TOKEN",
    help="Bearer token; auth disabled if omitted.",
)
@click.option(
    "--json-response/--sse-response",
    default=False,
    help="Return JSON instead of streaming SSE.",
)
def http(host: str | None, port: int | None, auth_token: str | None, json_response: bool) -> None:
    """Run the MCP server over streamable HTTP (for remote deployments)."""
    settings = load_settings()
    if host is not None:
        settings.host = host
    if port is not None:
        settings.port = port
    if auth_token is not None:
        from pydantic import SecretStr

        settings.auth_token = SecretStr(auth_token)

    _configure_logging(settings.log_level)
    mcp = create_server(settings)

    # FastMCP exposes a Starlette app for streamable-http; we wrap it for auth
    # and mount a small /health probe alongside it.
    app = mcp.streamable_http_app()
    app.router.routes.append(Route("/health", _health, methods=["GET"]))
    if json_response:
        # The FastMCP attribute lives on the session manager; set it before serving.
        mcp.settings.streamable_http_json_response = True  # type: ignore[attr-defined]

    token = settings.auth_token.get_secret_value() if settings.auth_token else ""
    if token:
        app.add_middleware(BearerAuthMiddleware, auth_token=token)
        logging.getLogger(__name__).info("Bearer token authentication enabled")
    else:
        logging.getLogger(__name__).warning(
            "No AUTH_TOKEN set — the HTTP endpoint is unauthenticated"
        )

    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower())


@main.command("gen-token")
@click.option("--length", default=32, show_default=True, help="Token byte length.")
def gen_token(length: int) -> None:
    """Print a cryptographically random bearer token suitable for AUTH_TOKEN."""
    click.echo(f"AUTH_TOKEN={secrets.token_urlsafe(length)}")


@main.command("list-tools")
def list_tools_cmd() -> None:
    """Print the names of all registered tools without starting the server."""
    tools = discover_predefined_tools()
    for tool in tools:
        click.echo(f"{tool.name:<45} {tool.source}")
    click.echo(f"{'get_database_schema':<45} (built-in)")
    click.echo(f"{'run_sql':<45} (built-in)")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
