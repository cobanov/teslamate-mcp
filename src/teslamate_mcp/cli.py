"""Command-line entry point for the TeslaMate MCP server."""

from __future__ import annotations

import asyncio
import logging
import secrets
import sys
from collections.abc import Awaitable, Callable

import click
import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import __version__
from .auth import BearerAuthMiddleware
from .config import load_settings
from .server import app_context_for, create_server
from .telemetry import configure_telemetry
from .tools import discover_predefined_tools
from .tools.apps_ui import APP_SPECS

# Kept well under the Dockerfile HEALTHCHECK timeout so the probe answers
# rather than being killed mid-flight.
_HEALTH_DB_TIMEOUT_S = 3.0


def _make_health(server: MCPServer) -> Callable[[Request], Awaitable[JSONResponse]]:
    """Build the /health handler bound to this server's connection pool."""

    async def _health(_request: Request) -> JSONResponse:
        """Readiness probe for the Docker HEALTHCHECK and any external monitor.

        This checks the database, not just the event loop. A liveness-only
        probe reported `ok` while every MCP call failed with a 500 because the
        pool could not reach PostgreSQL — the container looked healthy while
        being entirely unable to serve.
        """
        body: dict[str, object] = {"status": "ok", "version": __version__, "database": "ok"}
        context = app_context_for(server)
        if context is None or context.pool.closed:
            body |= {"status": "degraded", "database": "unavailable"}
            return JSONResponse(body, status_code=503)
        try:
            async with asyncio.timeout(_HEALTH_DB_TIMEOUT_S):
                async with context.pool.connection() as conn:
                    await conn.execute("SELECT 1")
        except Exception as exc:  # any failure here means "not serving"
            # Some psycopg errors stringify to "", and an empty str has no
            # lines at all — indexing it would 500 the probe it exists to keep
            # honest. Fall back to the class name.
            detail = next(iter(str(exc).strip().splitlines()), None) or type(exc).__name__
            body |= {"status": "degraded", "database": "unreachable", "detail": detail[:200]}
            return JSONResponse(body, status_code=503)
        return JSONResponse(body)

    return _health


class NormalizeMcpPathMiddleware:
    """Rewrite `/mcp/` to `/mcp` before routing so both forms work.

    SDK v1 mounted the transport (canonical `/mcp/`, bare `/mcp` redirected);
    SDK v2 routes it (canonical `/mcp`, `/mcp/` redirects). Deployed clients —
    notably the Cloudflare MCP portal, whose saved hostname is immutable — may
    have either form configured, and uvicorn's redirect behind a tunnel emits
    a malformed Location that Cloudflare rejects with error 1003.
    """

    def __init__(self, app) -> None:
        self._app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp/":
            scope = dict(scope)
            scope["path"] = "/mcp"
            scope["raw_path"] = b"/mcp"
        await self._app(scope, receive, send)


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
    configure_telemetry()
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
@click.option(
    "--stateless/--stateful",
    "stateless",
    default=False,
    help="Serve legacy-era clients without per-session state (2026-07-28 era "
    "requests are always stateless).",
)
def http(
    host: str | None,
    port: int | None,
    auth_token: str | None,
    json_response: bool,
    stateless: bool,
) -> None:
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
    configure_telemetry()
    mcp = create_server(settings)

    # MCPServer exposes a Starlette app for streamable-http; we wrap it for
    # auth and mount a small /health probe alongside it. The app's lifespan
    # runs the server lifespan once per process, which opens and closes the
    # shared pool. Passing the bind host lets the SDK auto-enable DNS-rebinding
    # protection for localhost binds (it stays off for 0.0.0.0 behind a proxy).
    app = mcp.streamable_http_app(
        json_response=json_response,
        stateless_http=stateless,
        host=settings.host,
    )
    app.router.routes.append(Route("/health", _make_health(mcp), methods=["GET"]))
    app.add_middleware(NormalizeMcpPathMiddleware)

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
        params = ", ".join(p.name for p in tool.params) or "no params"
        click.echo(f"{tool.name:<45} {tool.source}  ({params})")
    click.echo(f"{'get_database_schema':<45} (built-in)  (table, refresh)")
    click.echo(f"{'run_sql':<45} (built-in)  (query)")
    by_name = {t.name: t for t in tools}
    for spec in APP_SPECS:
        params = ", ".join(p.name for p in by_name[spec.query_name].params) or "no params"
        click.echo(f"{spec.tool_name:<45} (MCP App)   ({params})")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
