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
    assert len(tools) == 30
    # Spot-check that a few expected tools are present.
    assert "get_basic_car_information" in names
    assert "get_battery_health_summary" in names
    assert "get_unusual_power_consumption" in names
    assert "search_drives" in names
    assert "search_charging_sessions" in names
    assert "get_drive_details" in names
    assert "get_charging_curve" in names
    assert "get_charging_costs" in names
    assert "get_battery_capacity_trend" in names
    assert "get_vampire_drain" in names
    assert "get_charging_efficiency" in names
    assert "get_charging_by_geofence" in names
    assert "get_soc_hygiene" in names
    assert "get_period_comparison" in names
    assert "get_drive_route" in names


def test_each_tool_has_nonempty_metadata() -> None:
    for tool in discover_predefined_tools():
        assert tool.name.startswith(("get_", "search_"))
        assert len(tool.description) > 20
        assert tool.sql.strip().upper().startswith(("SELECT", "WITH"))


def test_every_tool_accepts_a_car_scope_or_is_id_scoped() -> None:
    # Every predefined report should be filterable by car unless it targets a
    # single entity by id (drive/charging session detail tools).
    id_scoped = {"get_drive_details", "get_charging_curve", "get_drive_route"}
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
        schema = tool.input_schema
        assert "ctx" not in schema.get("properties", {}), tool.name
        assert "ctx" not in schema.get("required", []), tool.name

    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert tools["run_sql"].input_schema["required"] == ["query"]


@pytest.mark.asyncio
async def test_parameterized_tool_schemas() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL)  # type: ignore[call-arg]
    mcp = create_server(settings)
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    search = tools["search_drives"].input_schema
    props = search["properties"]
    assert {"type": "string"} in props["car_name"]["anyOf"]  # nullable string
    assert props["car_name"]["default"] is None
    assert props["limit"]["default"] == 50
    assert props["limit"]["minimum"] == 1
    assert props["limit"]["maximum"] == 500
    assert props["order_by"]["enum"] == ["start_date", "distance", "duration"]
    assert props["order_by"]["default"] == "start_date"
    assert search.get("required", []) == []

    details = tools["get_drive_details"].input_schema
    assert details["required"] == ["drive_id"]
    assert details["properties"]["drive_id"]["type"] == "integer"

    degradation = tools["get_battery_degradation_over_time"].input_schema
    assert degradation["properties"]["days"]["default"] == 730

    costs = tools["get_charging_costs"].input_schema
    assert costs["properties"]["group_by"]["enum"] == ["month", "location", "car"]

    vampire = tools["get_vampire_drain"].input_schema
    assert vampire["properties"]["min_gap_hours"]["default"] == 5.0
    assert vampire["properties"]["limit"]["default"] == 20
    assert vampire.get("required", []) == []

    route = tools["get_drive_route"].input_schema
    assert route["required"] == ["drive_id"]
    assert route["properties"]["max_points"]["default"] == 200

    comparison = tools["get_period_comparison"].input_schema
    assert comparison["properties"]["days"]["default"] == 30

    schema_tool = tools["get_database_schema"].input_schema
    assert "table" in schema_tool["properties"]
    assert "table" not in schema_tool.get("required", [])


def _row_properties(output_schema: dict) -> dict:
    """Resolve the {result: [$ref]} wrapper to the row model's properties."""
    items = output_schema["properties"]["result"]["items"]
    if "$ref" in items:
        name = items["$ref"].rsplit("/", 1)[-1]
        return output_schema["$defs"][name]["properties"]
    return items.get("properties", {})


@pytest.mark.asyncio
async def test_typed_output_schemas_from_toml() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL)  # type: ignore[call-arg]
    mcp = create_server(settings)
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    # Every predefined tool declares [[output]] and gets per-column typing.
    for t in discover_predefined_tools():
        assert t.output, f"{t.source} has no [[output]] declaration"
        props = _row_properties(tools[t.name].output_schema)
        assert set(props) == {c.name for c in t.output}, t.name

    details = _row_properties(tools["get_drive_details"].output_schema)
    assert {"type": "integer"} in details["drive_id"]["anyOf"]  # nullable int
    assert {"type": "string"} in details["car_name"]["anyOf"]
    assert {"type": "number"} in details["distance_km"]["anyOf"]

    # run_sql stays deliberately untyped (arbitrary SELECTs).
    run_sql_items = tools["run_sql"].output_schema["properties"]["result"]["items"]
    assert run_sql_items.get("additionalProperties") is True


def test_output_contract_violations_raise(tmp_path: Path) -> None:
    (tmp_path / "q.sql").write_text("SELECT 1 AS a", encoding="utf-8")
    base = 'name = "x"\ndescription = "a perfectly valid description here"\n'

    (tmp_path / "q.toml").write_text(
        base + '[[output]]\nname = "a"\ntype = "decimal"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="unknown type"):
        discover_predefined_tools(tmp_path)

    (tmp_path / "q.toml").write_text(
        base
        + '[[output]]\nname = "a"\ntype = "integer"\n[[output]]\nname = "a"\ntype = "integer"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate output column"):
        discover_predefined_tools(tmp_path)

    (tmp_path / "q.toml").write_text(
        base + '[[output]]\nname = "a"\ntype = "integer"\nextra = 1\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="unknown output key"):
        discover_predefined_tools(tmp_path)
