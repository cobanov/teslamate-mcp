"""Tests for the MCP Apps extension (show_* tools + their ui:// apps)."""

from __future__ import annotations

import pytest

from teslamate_mcp.config import Settings
from teslamate_mcp.server import create_server
from teslamate_mcp.tools.apps_ui import (
    APP_SPECS,
    CHARGING_CURVE_APP_URI,
    build_apps_extension,
)

_DUMMY_DB_URL = "postgresql://teslamate:secret@example.test/teslamate"

# Seeded ids from conftest._SETUP_SQL.
_CURVE_SESSION_ID = 1  # 30 charge points, battery 50..79
_ROUTE_DRIVE_ID = 4  # fixed-date drive with 12 seeded track points

# Arguments that produce rows for each app tool against the seeded database.
_APP_ARGS = {
    "show_charging_curve": {"charging_process_id": _CURVE_SESSION_ID, "max_points": 10},
    "show_battery_degradation": {},
    "show_drive_route": {"drive_id": _ROUTE_DRIVE_ID},
}


def test_every_app_spec_has_seeded_args() -> None:
    assert set(_APP_ARGS) == {spec.tool_name for spec in APP_SPECS}


def _sans_title(schema: dict) -> dict:
    """The SDK titles schemas after the tool name; ignore that difference."""
    return {k: v for k, v in schema.items() if k != "title"}


@pytest.mark.asyncio
async def test_app_tools_declare_ui_binding() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL)  # type: ignore[call-arg]
    mcp = create_server(settings)
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    for spec in APP_SPECS:
        tool = tools[spec.tool_name]
        assert tool.meta == {"ui": {"resourceUri": spec.uri}}, spec.tool_name
        assert "ctx" not in tool.input_schema.get("properties", {}), spec.tool_name
        assert tool.annotations.read_only_hint is True
        # Drift-proof: the app tool exposes exactly its backing query's contract.
        backing = tools[spec.query_name]
        assert _sans_title(tool.input_schema) == _sans_title(backing.input_schema), spec.tool_name
        assert _sans_title(tool.output_schema) == _sans_title(backing.output_schema), spec.tool_name

    curve = tools["show_charging_curve"]
    assert curve.input_schema["required"] == ["charging_process_id"]
    assert curve.input_schema["properties"]["max_points"]["default"] == 120


def test_missing_curve_query_fails_fast() -> None:
    with pytest.raises(RuntimeError, match="get_charging_curve"):
        build_apps_extension([], report_timezone="UTC")


async def test_app_resources_served_with_mcp_app_mime(mcp_session) -> None:
    async with mcp_session() as session:
        resources = await session.list_resources()
        uris = {str(r.uri): r for r in resources.resources}
        assert CHARGING_CURVE_APP_URI in uris
        for spec in APP_SPECS:
            assert spec.uri in uris, spec.tool_name
            assert uris[spec.uri].mime_type == "text/html;profile=mcp-app"

            read = await session.read_resource(spec.uri)
            content = read.contents[0]
            assert content.mime_type == "text/html;profile=mcp-app"
            assert content.meta == {"ui": {"prefersBorder": True}}
            # The document must speak the ext-apps handshake and render offline.
            for marker in (
                "ui/initialize",
                "ui/notifications/initialized",
                "ui/notifications/tool-result",
                "ui/notifications/size-changed",
                "ui/resource-teardown",
            ):
                assert marker in content.text, (spec.tool_name, marker)
            # Self-contained: no external fetches.
            assert "https://" not in content.text, spec.tool_name


async def test_app_tools_match_their_plain_tools(mcp_session) -> None:
    async with mcp_session() as session:
        for spec in APP_SPECS:
            args = _APP_ARGS[spec.tool_name]
            app_result = await session.call_tool(spec.tool_name, args)
            plain_result = await session.call_tool(spec.query_name, args)
            assert not app_result.is_error, (
                spec.tool_name,
                [getattr(c, "text", c) for c in app_result.content],
            )
            rows = app_result.structured_content["result"]
            assert rows == plain_result.structured_content["result"], spec.tool_name
            assert rows, spec.tool_name  # seeded data must produce chartable rows

        curve_rows = (
            await session.call_tool("show_charging_curve", _APP_ARGS["show_charging_curve"])
        ).structured_content["result"]
        assert len(curve_rows) == 10
        assert {"bucket_start", "battery_level_start", "avg_power_kw"} <= set(curve_rows[0])

        route_rows = (
            await session.call_tool("show_drive_route", _APP_ARGS["show_drive_route"])
        ).structured_content["result"]
        assert {"point_order", "latitude", "longitude"} <= set(route_rows[0])


async def test_app_tool_results_carry_resource_link(mcp_session) -> None:
    """Claude's renderer keys off a resource_link in the result (in addition
    to tool _meta.ui); ResourceLinkedApps prepends one via intercept_tool_call."""
    async with mcp_session() as session:
        for spec in APP_SPECS:
            result = await session.call_tool(spec.tool_name, _APP_ARGS[spec.tool_name])
            assert not result.is_error, spec.tool_name
            link = result.content[0]
            assert link.type == "resource_link", spec.tool_name
            assert str(link.uri) == spec.uri
            assert link.mime_type == "text/html;profile=mcp-app"

        # Plain tools stay link-free.
        plain = await session.call_tool(
            "get_charging_curve", {"charging_process_id": _CURVE_SESSION_ID, "max_points": 10}
        )
        assert all(b.type != "resource_link" for b in plain.content)
