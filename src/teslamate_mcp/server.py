"""FastMCP server factory and lifespan management."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from mcp.server.fastmcp import FastMCP
from psycopg_pool import AsyncConnectionPool

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

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Per-process state exposed to tools via the request context."""

    pool: AsyncConnectionPool
    schema: list[dict[str, Any]] | None = field(default=None)


def create_server(settings: Settings) -> FastMCP:
    """Build the FastMCP server, wire up the lifespan, and register all tools."""

    # ONE pool + schema cache shared by every MCP session. FastMCP runs the
    # lifespan per *session*, not per process — opening (and never closing,
    # since clients rarely terminate sessions) a pool per session leaked
    # connections until Postgres ran out of slots and the transport died.
    app_context = AppContext(pool=build_pool(settings))
    init_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
        # Must never raise: an exception here kills the streamable-HTTP
        # session manager's task group and 500s every later request. On
        # failure, yield anyway — individual tool calls then surface the DB
        # error per call, and the next session retries the init.
        try:
            async with init_lock:
                await app_context.pool.open()  # idempotent on an open pool
                if app_context.schema is None:
                    app_context.schema = await load_schema(app_context.pool)
                    logger.info(
                        "Database pool opened (min=%d, max=%d); schema cached (%d columns)",
                        settings.pool_min_size,
                        settings.pool_max_size,
                        len(app_context.schema),
                    )
        except Exception:
            logger.exception("Deferred DB init failed; tool calls will error until it succeeds")
        yield app_context

    mcp = FastMCP(
        "teslamate",
        lifespan=lifespan,
        host=settings.host,
        port=settings.port,
        debug=settings.debug,
    )

    tools = discover_predefined_tools()
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
        "Registered %d predefined tools + run_sql + get_database_schema%s + 2 resources + prompts",
        len(tools),
        " + set_charging_cost (writes ENABLED)" if settings.enable_charging_writes else "",
    )

    # Exposed for process-shutdown hooks (cli.py) and test teardown.
    mcp.teslamate_app_context = app_context  # type: ignore[attr-defined]

    return mcp
