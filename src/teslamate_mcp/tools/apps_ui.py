"""MCP Apps extension: interactive charts rendered in-conversation.

Each `AppSpec` binds a bundled query to a self-contained HTML app
(ext-apps spec 2026-01-26) that the host renders in a sandboxed iframe.
Per SEP-2133 every app tool degrades gracefully: it returns the same rows
as its backing `get_*` query tool, so clients that did not negotiate the
Apps extension still get the data.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files

from mcp import types
from mcp.server.apps import APP_MIME_TYPE, Apps
from mcp.types import ToolAnnotations

from .registry import PredefinedTool, make_query_handler


@dataclass(frozen=True)
class AppSpec:
    """One UI-bound tool: a bundled query rendered by a bundled HTML app."""

    tool_name: str
    query_name: str
    uri: str
    html_file: str
    resource_name: str
    resource_title: str
    resource_description: str
    tool_description: str


APP_SPECS: tuple[AppSpec, ...] = (
    AppSpec(
        tool_name="show_charging_curve",
        query_name="get_charging_curve",
        uri="ui://teslamate/charging-curve.html",
        html_file="charging_curve.html",
        resource_name="charging_curve_chart",
        resource_title="Charging curve chart",
        resource_description=(
            "Interactive battery-level and charging-power chart for one session."
        ),
        tool_description=(
            "Render an interactive charging-curve chart for one charging session, "
            "displayed directly in the conversation (battery level and charging "
            "power over time, with hover readouts and a data table). Returns the "
            "same rows as get_charging_curve, so it also works as a plain data "
            "tool. Prefer this over get_charging_curve when the user wants to SEE "
            "the curve. Find session ids with search_charging_sessions."
        ),
    ),
    AppSpec(
        tool_name="show_battery_degradation",
        query_name="get_battery_degradation_over_time",
        uri="ui://teslamate/battery-degradation.html",
        html_file="battery_degradation.html",
        resource_name="battery_degradation_chart",
        resource_title="Battery degradation chart",
        resource_description=("Interactive monthly rated-range trend chart, one line per car."),
        tool_description=(
            "Render an interactive battery-degradation trend chart, displayed "
            "directly in the conversation (monthly average and best rated range "
            "at full charge, one line per car, with hover readouts and a data "
            "table). Returns the same rows as get_battery_degradation_over_time, "
            "so it also works as a plain data tool. Prefer this over "
            "get_battery_degradation_over_time when the user wants to SEE the "
            "trend."
        ),
    ),
    AppSpec(
        tool_name="show_drive_route",
        query_name="get_drive_route",
        uri="ui://teslamate/drive-route.html",
        html_file="drive_route.html",
        resource_name="drive_route_map",
        resource_title="Drive route map",
        resource_description=(
            "Interactive GPS route map with speed and battery readouts for one drive."
        ),
        tool_description=(
            "Render an interactive route map for one drive, displayed directly "
            "in the conversation (the GPS track with start/end markers, hover "
            "readouts for time, speed, and battery, and a waypoint table). "
            "Returns the same rows as get_drive_route, so it also works as a "
            "plain data tool. Prefer this over get_drive_route when the user "
            "wants to SEE the route. Find drive ids with search_drives."
        ),
    ),
)

CHARGING_CURVE_APP_URI = APP_SPECS[0].uri


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


def build_apps_extension(tools: list[PredefinedTool], *, report_timezone: str) -> Apps:
    """Build the Apps extension; pass the result to MCPServer(extensions=[...]).

    Each app tool reuses its backing query via make_query_handler, so the
    chart and the plain `get_*` tool can never drift apart (same params,
    same tz injection, same typed output schema).
    """
    by_name = {t.name: t for t in tools}

    apps = ResourceLinkedApps()

    annotations = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    for spec in APP_SPECS:
        query = by_name.get(spec.query_name)
        if query is None:  # fail fast, like a missing .toml sidecar
            raise RuntimeError(
                f"MCP Apps: bundled query '{spec.query_name}' not found; "
                f"required by {spec.tool_name} — its .sql/.toml must exist in queries/"
            )
        handler = make_query_handler(query, report_timezone=report_timezone)
        handler.__name__ = spec.tool_name
        handler.__doc__ = spec.tool_description
        apps.tool(
            resource_uri=spec.uri,
            name=spec.tool_name,
            description=spec.tool_description,
            annotations=annotations,
        )(handler)
        apps.add_html_resource(
            spec.uri,
            _load_app_html(spec.html_file),
            name=spec.resource_name,
            title=spec.resource_title,
            description=spec.resource_description,
            prefers_border=True,
        )
    return apps
