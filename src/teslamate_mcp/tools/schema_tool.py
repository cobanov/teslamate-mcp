"""The `get_database_schema` tool: live introspection of TeslaMate tables."""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..schema import load_schema

logger = logging.getLogger(__name__)


def register_schema_tool(mcp: MCPServer) -> None:
    """Register `get_database_schema` on the given server.

    The schema is fetched once at startup (cached on the lifespan context) so
    repeated tool calls do not re-query `information_schema`. The cache is
    refreshed on every server restart, so DDL changes are picked up there.
    """

    annotations = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    description = (
        "Explore the TeslaMate database schema. Without arguments: a compact "
        "list of every table with its column count. With `table`: full column "
        "detail (name, data type, nullability, position) for that table. Use "
        "this to discover available columns before writing custom SQL with "
        "`run_sql`."
    )

    async def get_database_schema(
        ctx: Context,
        table: str | None = Field(
            default=None,
            description="Table name for full column detail. Omit for a compact list of all tables.",
        ),
    ) -> list[dict[str, Any]]:
        lifespan_ctx = ctx.request_context.lifespan_context
        if lifespan_ctx.schema is None:
            logger.info("Schema cache cold — querying information_schema")
            lifespan_ctx.schema = await load_schema(lifespan_ctx.pool)
        rows = lifespan_ctx.schema

        if table is None:
            # Compact overview; the cache is ordered by schema/table/position,
            # so a plain dict preserves that order for the summary too.
            counts: dict[tuple[str, str], int] = {}
            for row in rows:
                key = (row["table_schema"], row["table_name"])
                counts[key] = counts.get(key, 0) + 1
            summary = [
                {"table_schema": schema, "table_name": name, "column_count": count}
                for (schema, name), count in counts.items()
            ]
            logger.info("Returning compact schema for %d tables", len(summary))
            return summary

        wanted = table.lower()
        detail = [row for row in rows if row["table_name"].lower() == wanted]
        if not detail:
            raise ValueError(
                f"Unknown table {table!r}. Call get_database_schema without "
                "arguments to list available tables."
            )
        logger.info("Returning %d columns for table %r", len(detail), table)
        return detail

    get_database_schema.__annotations__["ctx"] = Context
    mcp.tool(
        name="get_database_schema",
        description=description,
        annotations=annotations,
    )(get_database_schema)
