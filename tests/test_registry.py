"""Unit tests for predefined-tool discovery and generated tool schemas."""

from __future__ import annotations

from pathlib import Path

import pytest

from teslamate_mcp.config import Settings
from teslamate_mcp.server import create_server
from teslamate_mcp.tools.registry import discover_predefined_tools

_DUMMY_DB_URL = "postgresql://teslamate:secret@example.test/teslamate"


def test_discover_finds_all_bundled_tools() -> None:
    tools = discover_predefined_tools()
    names = {t.name for t in tools}
    assert len(tools) == 23
    # Spot-check that a few expected tools are present.
    assert "get_basic_car_information" in names
    assert "get_battery_health_summary" in names
    assert "get_unusual_power_consumption" in names
    assert "search_drives" in names
    assert "search_charging_sessions" in names
    assert "get_drive_details" in names
    assert "get_charging_curve" in names
    assert "get_charging_costs" in names


def test_each_tool_has_nonempty_metadata() -> None:
    for tool in discover_predefined_tools():
        assert tool.name.startswith(("get_", "search_"))
        assert len(tool.description) > 20
        assert tool.sql.strip().upper().startswith(("SELECT", "WITH"))


def test_every_tool_accepts_a_car_scope_or_is_id_scoped() -> None:
    # Every predefined report should be filterable by car unless it targets a
    # single entity by id (drive/charging session detail tools).
    id_scoped = {"get_drive_details", "get_charging_curve"}
    for tool in discover_predefined_tools():
        param_names = {p.name for p in tool.params}
        if tool.name in id_scoped:
            assert param_names & {"drive_id", "charging_process_id"}
        else:
            assert "car_name" in param_names, tool.name


def test_missing_sidecar_raises(tmp_path: Path) -> None:
    (tmp_path / "orphan.sql").write_text("SELECT 1", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Missing sidecar"):
        discover_predefined_tools(tmp_path)


def test_malformed_sidecar_raises(tmp_path: Path) -> None:
    (tmp_path / "q.sql").write_text("SELECT 1", encoding="utf-8")
    (tmp_path / "q.toml").write_text('name = "x"\n', encoding="utf-8")  # missing description
    with pytest.raises(ValueError, match="description"):
        discover_predefined_tools(tmp_path)


@pytest.mark.asyncio
async def test_tool_schemas_do_not_expose_context_argument() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL)  # type: ignore[call-arg]
    mcp = create_server(settings)

    for tool in await mcp.list_tools():
        schema = tool.inputSchema
        assert "ctx" not in schema.get("properties", {}), tool.name
        assert "ctx" not in schema.get("required", []), tool.name

    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert tools["run_sql"].inputSchema["required"] == ["query"]


@pytest.mark.asyncio
async def test_parameterized_tool_schemas() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL)  # type: ignore[call-arg]
    mcp = create_server(settings)
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    search = tools["search_drives"].inputSchema
    props = search["properties"]
    assert {"type": "string"} in props["car_name"]["anyOf"]  # nullable string
    assert props["car_name"]["default"] is None
    assert props["limit"]["default"] == 50
    assert props["limit"]["minimum"] == 1
    assert props["limit"]["maximum"] == 500
    assert props["order_by"]["enum"] == ["start_date", "distance", "duration"]
    assert props["order_by"]["default"] == "start_date"
    assert search.get("required", []) == []

    details = tools["get_drive_details"].inputSchema
    assert details["required"] == ["drive_id"]
    assert details["properties"]["drive_id"]["type"] == "integer"

    degradation = tools["get_battery_degradation_over_time"].inputSchema
    assert degradation["properties"]["days"]["default"] == 730

    costs = tools["get_charging_costs"].inputSchema
    assert costs["properties"]["group_by"]["enum"] == ["month", "location", "car"]

    schema_tool = tools["get_database_schema"].inputSchema
    assert "table" in schema_tool["properties"]
    assert "table" not in schema_tool.get("required", [])
