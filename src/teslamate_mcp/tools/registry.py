"""Discover and register predefined SQL-backed tools."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from ..db import fetch_all


@dataclass(frozen=True)
class PredefinedTool:
    """A SQL query exposed as an MCP tool, declared via a .sql + .toml pair."""

    name: str
    description: str
    sql: str
    source: str  # filename, for diagnostics


def _queries_dir() -> Path:
    """Locate the bundled `queries/` directory inside the installed package."""
    resource = files("teslamate_mcp").joinpath("queries")
    with as_file(resource) as path:
        return Path(path)


def discover_predefined_tools(directory: Path | None = None) -> list[PredefinedTool]:
    """Scan a directory for .sql files and load each one's sidecar .toml metadata.

    Each .sql file must have a sibling .toml with `name` and `description` keys.
    Missing sidecars raise FileNotFoundError so misconfiguration fails fast at
    startup rather than silently producing a half-empty tool list.
    """
    base = directory or _queries_dir()
    tools: list[PredefinedTool] = []
    for sql_path in sorted(base.glob("*.sql")):
        toml_path = sql_path.with_suffix(".toml")
        if not toml_path.exists():
            raise FileNotFoundError(
                f"Missing sidecar metadata for {sql_path.name}: expected {toml_path.name}"
            )
        meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        try:
            name = meta["name"]
            description = meta["description"]
        except KeyError as exc:
            raise ValueError(f"{toml_path.name} is missing required key {exc.args[0]!r}") from exc
        tools.append(
            PredefinedTool(
                name=name,
                description=description,
                sql=sql_path.read_text(encoding="utf-8"),
                source=sql_path.name,
            )
        )
    return tools


def register_predefined_tools(mcp: FastMCP, tools: list[PredefinedTool]) -> None:
    """Attach each predefined tool to the FastMCP server.

    A small factory captures the SQL per tool so the registered coroutine
    closes over only its own query — without a factory, every registered
    coroutine would share the loop variable and run the same SQL.
    """
    annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    for tool in tools:
        _register_one(mcp, tool, annotations)


def _register_one(mcp: FastMCP, tool: PredefinedTool, annotations: ToolAnnotations) -> None:
    async def handler(ctx: Context) -> list[dict[str, Any]]:
        pool = ctx.request_context.lifespan_context.pool
        await ctx.info(f"Running {tool.name} ({tool.source})")
        rows = await fetch_all(pool, tool.sql)
        await ctx.info(f"{tool.name} returned {len(rows)} row(s)")
        return rows

    handler.__name__ = tool.name
    handler.__doc__ = tool.description
    handler.__annotations__["ctx"] = Context
    mcp.tool(name=tool.name, description=tool.description, annotations=annotations)(handler)
