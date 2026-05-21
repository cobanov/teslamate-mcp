"""FastMCP server factory and lifespan management."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from mcp.server.fastmcp import FastMCP
from psycopg_pool import AsyncConnectionPool

from .config import Settings
from .db import build_pool
from .schema import load_schema
from .tools import (
    discover_predefined_tools,
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

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
        pool = build_pool(settings)
        await pool.open()
        logger.info(
            "Database pool opened (min=%d, max=%d)",
            settings.pool_min_size,
            settings.pool_max_size,
        )
        try:
            schema = await load_schema(pool)
            logger.info("Loaded schema: %d columns cached", len(schema))
            yield AppContext(pool=pool, schema=schema)
        finally:
            await pool.close()
            logger.info("Database pool closed")

    mcp = FastMCP(
        "teslamate",
        lifespan=lifespan,
        host=settings.host,
        port=settings.port,
        debug=settings.debug,
    )

    tools = discover_predefined_tools()
    register_predefined_tools(mcp, tools)
    register_schema_tool(mcp)
    register_custom_sql(
        mcp,
        statement_timeout_ms=settings.query_timeout_ms,
        row_limit=settings.custom_sql_row_limit,
    )
    logger.info("Registered %d predefined tools + run_sql + get_database_schema", len(tools))

    return mcp
