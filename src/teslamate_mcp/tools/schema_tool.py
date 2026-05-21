"""The `get_database_schema` tool: live introspection of TeslaMate tables."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from ..schema import load_schema


def register_schema_tool(mcp: FastMCP) -> None:
    """Register `get_database_schema` on the given server.

    The schema is fetched once at startup (cached on the lifespan context) so
    repeated tool calls do not re-query `information_schema`. The cache is
    refreshed on every server restart, so DDL changes are picked up there.
    """

    annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    description = (
        "Return the TeslaMate database schema: one row per column with "
        "table_schema, table_name, column_name, data_type, is_nullable, and "
        "ordinal_position. Use this to discover available columns before "
        "writing custom SQL with `run_sql`."
    )

    @mcp.tool(
        name="get_database_schema",
        description=description,
        annotations=annotations,
    )
    async def get_database_schema(ctx: Context) -> list[dict[str, Any]]:
        lifespan_ctx = ctx.request_context.lifespan_context
        if lifespan_ctx.schema is None:
            await ctx.info("Schema cache cold — querying information_schema")
            lifespan_ctx.schema = await load_schema(lifespan_ctx.pool)
        await ctx.info(f"Returning schema for {len(lifespan_ctx.schema)} columns")
        return lifespan_ctx.schema
