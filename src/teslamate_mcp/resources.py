"""MCP resources: predefined-query metadata exposed by URI.

Resource handlers in FastMCP cannot receive a Context, so anything that needs
runtime database access (like the live schema) stays in tool form. The
resources here are derived purely from the bundled SQL + TOML files, so they
are safe to serve as static-content URIs.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .tools.registry import PredefinedTool


def register_resources(mcp: FastMCP, tools: list[PredefinedTool]) -> None:
    """Expose the list of predefined queries and each query's raw SQL."""

    by_name: dict[str, PredefinedTool] = {t.name: t for t in tools}

    @mcp.resource(
        uri="teslamate://queries",
        name="Predefined query index",
        description="List of every predefined query tool with its description.",
        mime_type="application/json",
    )
    async def queries_index() -> str:
        index = [{"name": t.name, "description": t.description, "source": t.source} for t in tools]
        return json.dumps(index, indent=2)

    @mcp.resource(
        uri="teslamate://queries/{name}",
        name="Predefined query SQL",
        description="Raw SQL source for a named predefined query.",
        mime_type="text/sql",
    )
    async def query_sql(name: str) -> str:
        try:
            return by_name[name].sql
        except KeyError as exc:
            raise ValueError(f"Unknown query: {name}") from exc
