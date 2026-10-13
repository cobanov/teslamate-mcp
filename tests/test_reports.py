"""Chart-backing reports: get_activity_report, get_visited_places, get_drive_efficiency_points."""

from __future__ import annotations


async def _rows(session, tool: str, **args) -> list[dict]:
    result = await session.call_tool(tool, args)
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_activity_report_month_by_day(mcp_session) -> None:
    async with mcp_session(with_trips=True) as session:
        rows = await _rows(
            session, "get_activity_report", car_name="road tripper", year=2025, month=6
        )

    assert [r["bucket"] for r in rows] == [f"2025-06-{d:02d}" for d in range(1, 31)]
    by_day = {r["bucket"]: r for r in rows}
    trip_day = by_day["2025-06-10"]
    assert (trip_day["drives"], trip_day["distance_km"], trip_day["driving_hours"]) == (
        3,
        360.0,
        3.8,
    )
    assert trip_day["energy_used_kwh"] == 45.6  # 285 rated km x 0.16 kWh
    assert trip_day["wh_per_km"] == 127
    assert (trip_day["charging_sessions"], trip_day["kwh_added"]) == (2, 75.0)
    assert trip_day["charging_cost"] is None
    assert by_day["2025-06-11"]["drives"] == 2
    quiet = by_day["2025-06-01"]
    assert (quiet["drives"], quiet["distance_km"], quiet["wh_per_km"]) == (0, 0.0, None)


async def test_activity_report_year_by_month(mcp_session) -> None:
    async with mcp_session(with_trips=True) as session:
        rows = await _rows(
            session, "get_activity_report", car_name="road tripper", period="year", year=2025
        )

    assert [r["bucket"] for r in rows] == [f"2025-{m:02d}" for m in range(1, 13)]
    june = rows[5]
    assert (june["drives"], june["distance_km"], june["charging_sessions"]) == (5, 389.0, 2)
    assert sum(r["drives"] for r in rows) == 5


async def test_visited_places(mcp_session) -> None:
    async with mcp_session(with_trips=True) as session:
        rows = await _rows(session, "get_visited_places", car_name="road tripper")
        regulars = await _rows(
            session, "get_visited_places", car_name="road tripper", min_arrivals=2
        )

    by_place = {r["location"]: r for r in rows}
    assert rows[0]["location"] == "Kizilay Square"  # two arrivals
    kizilay = by_place["Kizilay Square"]
    assert (kizilay["arrivals"], kizilay["latitude"], kizilay["longitude"]) == (2, 39.92, 32.85)
    assert (kizilay["charging_sessions"], kizilay["kwh_added"]) == (1, 40.0)
    assert kizilay["parked_hours"] > 22.6  # overnight, plus the stay since the last drive
    supercharger = by_place["Supercharger Bolu"]
    assert (supercharger["arrivals"], supercharger["parked_hours"]) == (1, 1.2)
    assert (supercharger["charging_sessions"], supercharger["kwh_added"]) == (1, 35.0)
    assert [r["location"] for r in regulars] == ["Kizilay Square"]


async def test_drive_efficiency_points(mcp_session) -> None:
    async with mcp_session(seeds=["estimate"]) as session:
        rows = await _rows(session, "get_drive_efficiency_points", car_name="planner")
        long_only = await _rows(
            session, "get_drive_efficiency_points", car_name="planner", min_distance_km=50
        )
        newest = await _rows(session, "get_drive_efficiency_points", car_name="planner", limit=3)

    assert len(rows) == 15
    assert {(r["outside_temp"], r["wh_per_km"]) for r in rows} == {
        (20.0, 150),
        (0.0, 210),
        (20.0, 180),
    }
    assert {(r["distance_km"], r["avg_speed_kmh"], r["wh_per_km"]) for r in long_only} == {
        (100.0, 100.0, 180)
    }
    assert len(newest) == 3
    assert [r["start_date"] for r in newest] == sorted(
        (r["start_date"] for r in newest), reverse=True
    )
