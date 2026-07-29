"""MCPServer factory and lifespan management."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.server import CacheHint
from psycopg_pool import AsyncConnectionPool

from . import __version__
from .config import Settings
from .db import build_pool
from .prompts import register_prompts
from .resources import register_resources
from .schema import load_schema
from .tools import (
    discover_predefined_tools,
    register_charging_write_tools,
    register_custom_sql,
    register_predefined_tools,
    register_schema_tool,
)
from .tools.apps_ui import build_apps_extension

logger = logging.getLogger(__name__)

# The tool/prompt/resource registry is fixed for the lifetime of the process
# (queries are bundled files, discovered once at startup), so clients may cache
# list results for a long time. "private" because the endpoint is authenticated.
_LIST_CACHE_HINT = CacheHint(ttl_ms=3_600_000, scope="private")
_CACHE_HINTS = {
    "server/discover": _LIST_CACHE_HINT,
    "tools/list": _LIST_CACHE_HINT,
    "prompts/list": _LIST_CACHE_HINT,
    "resources/list": _LIST_CACHE_HINT,
    "resources/templates/list": _LIST_CACHE_HINT,
    "resources/read": _LIST_CACHE_HINT,
}


@dataclass
class AppContext:
    """Per-process state exposed to tools via the request context."""

    pool: AsyncConnectionPool
    schema: list[dict[str, Any]] | None = field(default=None)


def create_server(settings: Settings) -> MCPServer:
    """Build the MCPServer, wire up the lifespan, and register all tools."""

    app_context = AppContext(pool=build_pool(settings))

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
        # On HTTP and stdio, SDK v2 enters this once per process; the in-memory
        # transport (tests) enters it once per sequential client connection, so
        # a closed pool is rebuilt on re-entry (psycopg pools cannot reopen).
        # Must never raise: a database that is down at boot should degrade to
        # per-call tool errors, not kill the transport — get_database_schema
        # lazily retries the schema load on first use.
        if app_context.pool.closed:
            app_context.pool = build_pool(settings)
        try:
            await app_context.pool.open()
            app_context.schema = await load_schema(app_context.pool)
            logger.info(
                "Database pool opened (min=%d, max=%d); schema cached (%d columns)",
                settings.pool_min_size,
                settings.pool_max_size,
                len(app_context.schema),
            )
        except Exception:
            logger.exception("DB init failed; tool calls will error until the DB is reachable")
        try:
            yield app_context
        finally:
            await app_context.pool.close()

    tools = discover_predefined_tools()

    mcp = MCPServer(
        "teslamate",
        version=__version__,
        lifespan=lifespan,
        debug=settings.debug,
        cache_hints=_CACHE_HINTS,
        # MCP Apps (io.modelcontextprotocol/ui): show_charging_curve + its
        # ui:// chart resource. Degrades to a plain data tool on clients
        # that did not negotiate the extension.
        extensions=[build_apps_extension(tools)],
    )

    register_predefined_tools(mcp, tools, report_timezone=settings.report_timezone)
    register_schema_tool(mcp)
    register_custom_sql(
        mcp,
        statement_timeout_ms=settings.query_timeout_ms,
        row_limit=settings.custom_sql_row_limit,
    )
    if settings.enable_charging_writes:
        register_charging_write_tools(mcp)
    register_resources(mcp, tools)
    register_prompts(mcp)
    logger.info(
        "Registered %d predefined tools + run_sql + get_database_schema + "
        "show_charging_curve (MCP Apps)%s + resources + prompts",
        len(tools),
        " + set_charging_cost (writes ENABLED)" if settings.enable_charging_writes else "",
    )

    # Exposed for process-shutdown hooks (cli.py) and test teardown.
    mcp.teslamate_app_context = app_context  # type: ignore[attr-defined]

    return mcp
