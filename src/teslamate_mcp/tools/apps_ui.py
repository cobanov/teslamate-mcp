"""MCP Apps extension: interactive charts rendered in-conversation.

Pilot app: `show_charging_curve` binds the bundled charging_curve.sql query to
a self-contained HTML chart (`ui://teslamate/charging-curve.html`) that the
host renders in a sandboxed iframe (ext-apps spec 2026-01-26). Per SEP-2133
the tool degrades gracefully: it returns the same rows as `get_charging_curve`,
so clients that did not negotiate the Apps extension still get the data.
"""

from __future__ import annotations

import logging
from importlib.resources import files
from typing import Any

from mcp import types
from mcp.server.apps import APP_MIME_TYPE, Apps
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from ..db import fetch_all
from .registry import PredefinedTool, build_row_model

logger = logging.getLogger(__name__)

CHARGING_CURVE_APP_URI = "ui://teslamate/charging-curve.html"


class ResourceLinkedApps(Apps):
    """Apps variant that also embeds a resource_link block in tool results.

    The ext-apps spec binds a tool to its UI via tool `_meta.ui` only, but
    Claude's connector implementation documents the interactive pattern as the
    result carrying "structuredContent and a resource link". Prepending the
    link is spec-harmless (non-UI clients ignore the extra block) and gives
    renderers that key off the result a second signal.
    """

    async def intercept_tool_call(self, params, ctx, call_next):  # type: ignore[override]
        result = await call_next(ctx)
        uri = next((u for b, u in self._tools if b.kwargs.get("name") == params.name), None)
        if uri is not None and isinstance(result, types.CallToolResult):
            result.content.insert(
                0,
                types.ResourceLink(
                    type="resource_link",
                    uri=uri,
                    name=uri.rsplit("/", 1)[-1],
                    mime_type=APP_MIME_TYPE,
                ),
            )
        return result


def _load_app_html(filename: str) -> str:
    return files("teslamate_mcp").joinpath("apps", filename).read_text(encoding="utf-8")


def build_apps_extension(tools: list[PredefinedTool]) -> Apps:
    """Build the Apps extension; pass the result to MCPServer(extensions=[...]).

    Reuses the bundled charging_curve.sql so the chart and the plain
    `get_charging_curve` tool can never drift apart.
    """
    try:
        curve = next(t for t in tools if t.name == "get_charging_curve")
    except StopIteration:  # fail fast, like a missing .toml sidecar
        raise RuntimeError(
            "MCP Apps: bundled query 'get_charging_curve' not found; "
            "charging_curve.sql/.toml must exist in queries/"
        ) from None

    apps = ResourceLinkedApps()

    annotations = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    description = (
        "Render an interactive charging-curve chart for one charging session, "
        "displayed directly in the conversation (battery level and charging "
        "power over time, with hover readouts and a data table). Returns the "
        "same rows as get_charging_curve, so it also works as a plain data "
        "tool. Prefer this over get_charging_curve when the user wants to SEE "
        "the curve. Find session ids with search_charging_sessions."
    )

    @apps.tool(
        resource_uri=CHARGING_CURVE_APP_URI,
        name="show_charging_curve",
        description=description,
        annotations=annotations,
    )
    async def show_charging_curve(
        ctx: Context,
        charging_process_id: int = Field(
            ...,
            description="The charging session's id, as returned by search_charging_sessions.",
        ),
        max_points: int = Field(
            120,
            ge=10,
            le=1000,
            description="Maximum number of curve points (time buckets) to return.",
        ),
    ) -> list[dict[str, Any]]:
        pool = ctx.request_context.lifespan_context.pool
        logger.info(
            "show_charging_curve rendering session %d (max_points=%d)",
            charging_process_id,
            max_points,
        )
        rows = await fetch_all(
            pool,
            curve.sql,
            {"charging_process_id": charging_process_id, "max_points": max_points},
        )
        logger.info("show_charging_curve returned %d point(s)", len(rows))
        return rows

    show_charging_curve.__annotations__["ctx"] = Context
    # Share the curve tool's [[output]] declaration so both tools advertise
    # the same typed outputSchema.
    row_model = build_row_model(curve)
    if row_model is not None:
        show_charging_curve.__annotations__["return"] = list[row_model]
    apps.add_html_resource(
        CHARGING_CURVE_APP_URI,
        _load_app_html("charging_curve.html"),
        name="charging_curve_chart",
        title="Charging curve chart",
        description="Interactive battery-level and charging-power chart for one session.",
        prefers_border=True,
    )
    return apps
