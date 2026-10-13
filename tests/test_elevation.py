"""Elevation: get_efficiency_by_elevation, ascent/descent, and route elevation."""

from __future__ import annotations


async def _rows(session, tool: str, **args) -> list[dict]:
    result = await session.call_tool(tool, args)
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_efficiency_by_elevation_groups_by_net_climb(mcp_session) -> None:
    async with mcp_session(seeds=["estimate"]) as session:
        rows = await _rows(session, "get_efficiency_by_elevation", car_name="planner")

    assert [
        (r["climb"], r["drives"], r["avg_net_climb_m_per_km"], r["wh_per_km"], r["vs_flat_pct"])
        for r in rows
    ] == [
        ("slight downhill (3-10 m/km)", 5, -5.0, 150, -16.7),
        ("flat (within 3 m/km)", 5, 0.0, 180, 0.0),
        ("uphill (more than 10 m/km)", 5, 15.0, 210, 16.7),
    ]
    flat = rows[1]
    # 1000 m up and 1000 m down per 100 km: flat, however much GPS noise adds.
    assert (flat["distance_km"], flat["avg_ascent_m_per_km"]) == (500.0, 10.0)


async def test_ascent_and_elevation_in_drive_and_trip_tools(mcp_session) -> None:
    async with mcp_session(with_trips=True) as session:
        details = await _rows(session, "get_drive_details", drive_id=4)
        route = await _rows(session, "get_drive_route", drive_id=4)
        trips = await _rows(session, "get_trips", car_name="road tripper")

    assert (details[0]["ascent_m"], details[0]["descent_m"]) == (120, 10)
    assert [p["elevation_m"] for p in route] == [100 + 10 * n for n in range(12)]
    road_trip = next(t for t in trips if t["trip_id"] == 101)
    assert (road_trip["ascent_m"], road_trip["descent_m"]) == (300, 150)  # three legs
