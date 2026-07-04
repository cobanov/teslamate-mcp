"""End-to-end tool tests against a real Postgres via an in-memory MCP session.

These run the full FastMCP stack (lifespan, pool, dispatch, param binding) and
are the safety net for SQL-level mistakes: missing ::casts on NULL params,
unescaped %, and column typos across all bundled queries.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.shared.memory import create_connected_server_and_client_session

from teslamate_mcp.config import Settings
from teslamate_mcp.server import create_server
from teslamate_mcp.tools.registry import discover_predefined_tools

# Seeded ids from conftest._SETUP_SQL (SERIAL columns reset on every reseed).
_TZ_BOUNDARY_DRIVE_ID = 4  # 2026-01-15 22:30 UTC = 2026-01-16 01:30 Europe/Istanbul
_CURVE_SESSION_ID = 1  # 30 charge points, battery 50..79
_REQUIRED_ARG_SEEDS = {"drive_id": _TZ_BOUNDARY_DRIVE_ID, "charging_process_id": _CURVE_SESSION_ID}


def rows_from(result) -> list[dict[str, Any]]:
    assert not result.isError, [getattr(c, "text", c) for c in result.content]
    if result.structuredContent is not None:
        return result.structuredContent["result"]
    return [json.loads(c.text) for c in result.content]


async def test_every_predefined_tool_runs_with_defaults(mcp_session) -> None:
    async with mcp_session() as session:
        for tool in discover_predefined_tools():
            args = {p.name: _REQUIRED_ARG_SEEDS[p.name] for p in tool.params if p.required}
            result = await session.call_tool(tool.name, args)
            assert not result.isError, (
                tool.name,
                [getattr(c, "text", c) for c in result.content],
            )


async def test_car_name_filter_binds(mcp_session) -> None:
    async with mcp_session() as session:
        rows = rows_from(
            await session.call_tool("get_total_distance_and_efficiency", {"car_name": "blue"})
        )
        assert len(rows) == 1
        assert "Blue Thunder" in rows[0].values()


async def test_zero_arg_charging_summary_parity(mcp_session) -> None:
    async with mcp_session() as session:
        rows = rows_from(await session.call_tool("get_all_charging_sessions_summary", {}))
        assert len(rows) == 2  # both cars, whole history
        blue = next(r for r in rows if "Blue Thunder" in r.values())
        values = set(blue.values())
        assert 80.0 in values  # 30 + 50 kWh
        assert 42.5 in values  # 12.50 + 30.00 cost


async def test_search_drives_location_and_min_distance(mcp_session) -> None:
    async with mcp_session() as session:
        rows = rows_from(
            await session.call_tool("search_drives", {"location": "edirne", "min_distance_km": 100})
        )
        assert len(rows) == 1
        assert rows[0]["distance_km"] == 120.0


async def test_search_drives_order_by_distance(mcp_session) -> None:
    async with mcp_session() as session:
        rows = rows_from(
            await session.call_tool("search_drives", {"order_by": "distance", "limit": 2})
        )
        assert len(rows) == 2
        assert rows[0]["distance_km"] >= rows[1]["distance_km"]
        assert rows[0]["distance_km"] == 120.0


async def test_search_drives_date_range(mcp_session) -> None:
    async with mcp_session() as session:
        rows = rows_from(
            await session.call_tool(
                "search_drives", {"start_date": "2026-01-01", "end_date": "2026-01-31"}
            )
        )
        assert [r["drive_id"] for r in rows] == [_TZ_BOUNDARY_DRIVE_ID]


async def test_limit_param(mcp_session) -> None:
    async with mcp_session() as session:
        rows = rows_from(await session.call_tool("get_longest_drives_by_distance", {"limit": 1}))
        assert len(rows) == 1
        assert rows[0]["distance_km"] == 120.0


async def test_get_drive_details(mcp_session) -> None:
    async with mcp_session() as session:
        rows = rows_from(
            await session.call_tool("get_drive_details", {"drive_id": _TZ_BOUNDARY_DRIVE_ID})
        )
        assert len(rows) == 1
        assert rows[0]["distance_km"] == 42.0
        assert rows[0]["car_name"] == "Blue Thunder"


async def test_missing_required_arg_errors(mcp_session) -> None:
    async with mcp_session() as session:
        result = await session.call_tool("get_drive_details", {})
        assert result.isError


async def test_charging_curve_downsamples(mcp_session) -> None:
    async with mcp_session() as session:
        rows = rows_from(
            await session.call_tool(
                "get_charging_curve",
                {"charging_process_id": _CURVE_SESSION_ID, "max_points": 10},
            )
        )
        assert len(rows) == 10  # 30 points into 10 buckets
        assert rows[0]["battery_level_start"] == 50
        starts = [r["bucket_start"] for r in rows]
        assert starts == sorted(starts)

        below_minimum = await session.call_tool(
            "get_charging_curve",
            {"charging_process_id": _CURVE_SESSION_ID, "max_points": 5},
        )
        assert below_minimum.isError  # contract minimum is 10


async def test_charging_costs_group_by(mcp_session) -> None:
    async with mcp_session() as session:
        by_car = rows_from(await session.call_tool("get_charging_costs", {"group_by": "car"}))
        assert {r["group_key"] for r in by_car} == {"Blue Thunder", "Red Rocket"}

        by_location = rows_from(
            await session.call_tool("get_charging_costs", {"group_by": "location"})
        )
        assert {r["group_key"] for r in by_location} == {"Home Street 1", "Supercharger Edirne"}


async def test_report_timezone_shifts_day_buckets(mcp_session) -> None:
    async with mcp_session() as session:
        utc_days = json.dumps(rows_from(await session.call_tool("get_drive_summary_per_day", {})))
    async with mcp_session(report_timezone="Europe/Istanbul") as session:
        ist_days = json.dumps(rows_from(await session.call_tool("get_drive_summary_per_day", {})))
    # 22:30 UTC on Jan 15 is 01:30 on Jan 16 in Istanbul (UTC+3).
    assert "2026-01-15" in utc_days and "2026-01-16" not in utc_days
    assert "2026-01-16" in ist_days and "2026-01-15" not in ist_days


async def test_sessions_share_one_pool(seeded_database) -> None:
    """Regression: per-session pools leaked one Postgres connection set per MCP
    session (clients rarely terminate sessions) until the server ran out of
    connection slots and the streamable-HTTP transport died."""
    settings = Settings(database_url=seeded_database)  # type: ignore[call-arg]
    mcp = create_server(settings)
    ctx = mcp.teslamate_app_context  # type: ignore[attr-defined]
    try:
        for _ in range(3):
            async with create_connected_server_and_client_session(
                mcp._mcp_server, raise_exceptions=False
            ) as session:
                result = await session.call_tool("get_basic_car_information", {})
                assert not result.isError
        # The pool survived every session exit — shared, not per-session.
        assert not ctx.pool.closed
    finally:
        await ctx.pool.close()


async def test_schema_tool_compact_and_detail(mcp_session) -> None:
    async with mcp_session() as session:
        compact = rows_from(await session.call_tool("get_database_schema", {}))
        cars_row = next(r for r in compact if r["table_name"] == "cars")
        assert cars_row["column_count"] == 7
        assert all("column_name" not in r for r in compact)

        detail = rows_from(await session.call_tool("get_database_schema", {"table": "cars"}))
        assert len(detail) == 7
        assert all(r["table_name"] == "cars" and "data_type" in r for r in detail)

        unknown = await session.call_tool("get_database_schema", {"table": "not_a_table"})
        assert unknown.isError
