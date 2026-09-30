"""Tests for the MCP Apps extension (show_* tools + their ui:// apps)."""

from __future__ import annotations

import pytest

from teslamate_mcp.config import Settings
from teslamate_mcp.server import create_server
from teslamate_mcp.tools.apps_ui import (
    APP_SPECS,
    CHARGING_CURVE_APP_URI,
    MAP_TILE_HOST,
    _load_app_html,
    _render_app_html,
    build_apps_extension,
)

_DUMMY_DB_URL = "postgresql://teslamate:secret@example.test/teslamate"

# Seeded ids from conftest._SETUP_SQL.
_CURVE_SESSION_ID = 1  # 30 charge points, battery 50..79
_ROUTE_DRIVE_ID = 4  # fixed-date drive with 12 seeded track points
_TRIP_ID = 101  # the car-3 road trip (mcp_session(with_trips=True))

# Arguments that produce rows for each app tool against the seeded database.
_APP_ARGS = {
    "show_charging_curve": {"charging_process_id": _CURVE_SESSION_ID, "max_points": 10},
    "show_battery_degradation": {},
    "show_drive_route": {"drive_id": _ROUTE_DRIVE_ID},
    "show_trip_route": {"trip_id": _TRIP_ID},
    "show_charging_curve_comparison": {},  # the base seed's DC session
    "show_activity_report": {},  # every day of the current month, empty or not
    "show_visited_places": {},
    "show_efficiency_vs_temperature": {},
    "show_recap": {},  # always one row, even for a quiet period
}
# Views that draw a basemap.
_MAP_VIEWS = {"show_drive_route", "show_trip_route", "show_visited_places"}


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
        assert tool.meta == {"ui": {"resourceUri": spec.uri}, "ui/resourceUri": spec.uri}, (
            spec.tool_name
        )
        assert "ctx" not in tool.input_schema.get("properties", {}), spec.tool_name
        assert tool.annotations.read_only_hint is True
        # Drift-proof: the app tool exposes exactly its backing query's contract.
        backing = tools[spec.query_name]
        assert _sans_title(tool.input_schema) == _sans_title(backing.input_schema), spec.tool_name
        assert _sans_title(tool.output_schema) == _sans_title(backing.output_schema), spec.tool_name

    curve = tools["show_charging_curve"]
    assert curve.input_schema["required"] == ["charging_process_id"]
    assert curve.input_schema["properties"]["max_points"]["default"] == 120


@pytest.mark.parametrize("spec", APP_SPECS, ids=lambda s: s.tool_name)
def test_app_handshake_matches_ext_apps_schema(spec) -> None:
    """Hosts validate ui/initialize against McpUiInitializeRequest and deliver
    tool data only after `initialized`; a wrong field name leaves the view
    empty. Regression: the apps sent `clientInfo` instead of `appInfo`."""
    html = _load_app_html(spec.html_file)
    init = html[html.index('request("ui/initialize"') :]
    init = init[: init.index("})")]
    for field in ("protocolVersion:", "appInfo:", "appCapabilities:"):
        assert field in init, (spec.tool_name, field)
    assert "clientInfo" not in init, spec.tool_name
    # Host requests that expect a response must get one.
    assert 'msg.method === "ping"' in html, spec.tool_name
    assert 'msg.method === "ui/resource-teardown"' in html, spec.tool_name


def test_app_uris_are_content_fingerprinted() -> None:
    """Hosts cache views by URI; a changed view must get a new one."""
    import hashlib
    import re

    for spec in APP_SPECS:
        match = re.fullmatch(r"ui://teslamate/([0-9a-f]{12})/([a-z-]+\.html)", spec.uri)
        assert match, spec.uri
        html = _render_app_html(spec.html_file, True)
        assert match.group(1) == hashlib.sha256(html.encode("utf-8")).hexdigest()[:12]
        assert spec.base_uri.endswith("/" + match.group(2))
    assert len({spec.uri for spec in APP_SPECS}) == len(APP_SPECS)


async def _drive_route_resource(*, map_tiles: bool):
    settings = Settings(database_url=_DUMMY_DB_URL, map_tiles=map_tiles)  # type: ignore[call-arg]
    mcp = create_server(settings)
    (resource,) = [r for r in await mcp.list_resources() if "drive-route" in str(r.uri)]
    (content,) = await mcp.read_resource(str(resource.uri))
    tool = next(t for t in await mcp.list_tools() if t.name == "show_drive_route")
    return resource, content.content, tool


@pytest.mark.asyncio
async def test_map_tiles_on_declares_basemap_host() -> None:
    resource, html, tool = await _drive_route_resource(map_tiles=True)
    assert resource.meta["ui"]["csp"] == {"resourceDomains": [MAP_TILE_HOST]}
    assert f'"{MAP_TILE_HOST}"' in html
    assert "__MAP_TILE_HOST__" not in html
    assert tool.meta["ui"]["resourceUri"] == str(resource.uri)


@pytest.mark.asyncio
async def test_map_tiles_off_keeps_view_self_contained() -> None:
    resource, html, tool = await _drive_route_resource(map_tiles=False)
    on_resource, _, _ = await _drive_route_resource(map_tiles=True)
    assert "csp" not in resource.meta["ui"]
    assert "https://" not in html
    assert "__MAP_TILE_HOST__" not in html
    # A settings change must not reuse a host's cached copy of the other variant.
    assert str(resource.uri) != str(on_resource.uri)
    assert tool.meta["ui"]["resourceUri"] == str(resource.uri)


def test_only_the_map_views_use_tiles() -> None:
    for spec in APP_SPECS:
        on = _render_app_html(spec.html_file, True)
        assert ("https://" in on) is (spec.tool_name in _MAP_VIEWS), spec.tool_name


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
            expected_ui: dict = {"prefersBorder": True}
            if spec.tool_name in _MAP_VIEWS:  # basemap tiles (MAP_TILES default on)
                expected_ui["csp"] = {"resourceDomains": [MAP_TILE_HOST]}
            assert content.meta == {"ui": expected_ui}
            # The document must speak the ext-apps handshake and render offline.
            for marker in (
                "ui/initialize",
                "ui/notifications/initialized",
                "ui/notifications/tool-result",
                "ui/notifications/size-changed",
                "ui/resource-teardown",
            ):
                assert marker in content.text, (spec.tool_name, marker)
            # No external fetches beyond the declared basemap host.
            external = content.text.replace(MAP_TILE_HOST, "")
            assert "https://" not in external, spec.tool_name


async def test_app_tools_match_their_plain_tools(mcp_session) -> None:
    async with mcp_session(with_trips=True) as session:
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


async def test_app_tool_results_carry_no_resource_link(mcp_session) -> None:
    """Regression (0.9.1): 0.8.0 prepended a result-level resource_link as a
    second rendering signal, but Claude Desktop renders a visible "Resource
    links are not currently supported" notice for it instead of ignoring it.
    App tools bind their UI via tool _meta.ui only — results must stay
    link-free."""
    async with mcp_session(with_trips=True) as session:
        for spec in APP_SPECS:
            result = await session.call_tool(spec.tool_name, _APP_ARGS[spec.tool_name])
            assert not result.is_error, spec.tool_name
            assert all(b.type != "resource_link" for b in result.content), spec.tool_name

        plain = await session.call_tool(
            "get_charging_curve", {"charging_process_id": _CURVE_SESSION_ID, "max_points": 10}
        )
        assert all(b.type != "resource_link" for b in plain.content)
