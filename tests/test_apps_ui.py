"""Tests for the MCP Apps extension (show_charging_curve + ui:// chart)."""

from __future__ import annotations

import pytest

from teslamate_mcp.config import Settings
from teslamate_mcp.server import create_server
from teslamate_mcp.tools.apps_ui import CHARGING_CURVE_APP_URI, build_apps_extension

_DUMMY_DB_URL = "postgresql://teslamate:secret@example.test/teslamate"

# Seeded ids from conftest._SETUP_SQL.
_CURVE_SESSION_ID = 1  # 30 charge points, battery 50..79


@pytest.mark.asyncio
async def test_app_tool_declares_ui_binding() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL)  # type: ignore[call-arg]
    mcp = create_server(settings)
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    tool = tools["show_charging_curve"]
    assert tool.meta == {"ui": {"resourceUri": CHARGING_CURVE_APP_URI}}
    assert tool.input_schema["required"] == ["charging_process_id"]
    assert "ctx" not in tool.input_schema.get("properties", {})
    assert tool.input_schema["properties"]["max_points"]["default"] == 120
    assert tool.annotations.read_only_hint is True


def test_missing_curve_query_fails_fast() -> None:
    with pytest.raises(RuntimeError, match="get_charging_curve"):
        build_apps_extension([])


async def test_app_resource_served_with_mcp_app_mime(mcp_session) -> None:
    async with mcp_session() as session:
        resources = await session.list_resources()
        uris = {str(r.uri): r for r in resources.resources}
        assert CHARGING_CURVE_APP_URI in uris
        assert uris[CHARGING_CURVE_APP_URI].mime_type == "text/html;profile=mcp-app"

        read = await session.read_resource(CHARGING_CURVE_APP_URI)
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
            assert marker in content.text, marker
        assert "https://" not in content.text  # self-contained: no external fetches


async def test_show_charging_curve_matches_plain_tool(mcp_session) -> None:
    async with mcp_session() as session:
        args = {"charging_process_id": _CURVE_SESSION_ID, "max_points": 10}
        app_result = await session.call_tool("show_charging_curve", args)
        plain_result = await session.call_tool("get_charging_curve", args)
        assert not app_result.is_error, [getattr(c, "text", c) for c in app_result.content]
        rows = app_result.structured_content["result"]
        assert rows == plain_result.structured_content["result"]
        assert len(rows) == 10
        assert {"bucket_start", "battery_level_start", "avg_power_kw"} <= set(rows[0])


async def test_app_tool_result_carries_resource_link(mcp_session) -> None:
    """Claude's renderer keys off a resource_link in the result (in addition
    to tool _meta.ui); ResourceLinkedApps prepends one via intercept_tool_call."""
    async with mcp_session() as session:
        result = await session.call_tool(
            "show_charging_curve", {"charging_process_id": _CURVE_SESSION_ID, "max_points": 10}
        )
        assert not result.is_error
        link = result.content[0]
        assert link.type == "resource_link"
        assert str(link.uri) == CHARGING_CURVE_APP_URI
        assert link.mime_type == "text/html;profile=mcp-app"

        # The plain tool stays link-free.
        plain = await session.call_tool(
            "get_charging_curve", {"charging_process_id": _CURVE_SESSION_ID, "max_points": 10}
        )
        assert all(b.type != "resource_link" for b in plain.content)
