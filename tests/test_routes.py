"""get_frequent_routes against car 13 ("Commuter", conftest._ROUTES_SQL)."""

from __future__ import annotations

_CAR = "Commuter"


async def _rows(session, **args) -> list[dict]:
    result = await session.call_tool("get_frequent_routes", {"car_name": _CAR, **args})
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_routes_merge_nearby_parking_spots(mcp_session) -> None:
    async with mcp_session(seeds=["routes"]) as session:
        rows = await _rows(session)
        tight = await _rows(session, place_radius_m=50)

    # Each direction is its own route; the single cabin drive is not a route.
    assert [(r["start_location"], r["end_location"], r["drives"]) for r in rows] == [
        ("Commuter Home", "Commuter Office", 4),
        ("Commuter Office", "Commuter Home", 3),
    ]
    out, back = rows
    assert out["departure_hour"] is None
    assert (out["typical_distance_km"], out["total_distance_km"]) == (20.0, 82.0)
    assert out["typical_duration_min"] == 33  # median of 30, 32, 34, 40
    assert (out["fastest_duration_min"], out["fastest_drive_id"]) == (30, 601)
    assert (out["slowest_duration_min"], out["slowest_drive_id"]) == (40, 603)
    assert (out["avg_speed_kmh"], out["wh_per_km"]) == (36.2, 120)
    assert out["usual_departure_local"] == "08:00"
    assert (back["typical_duration_min"], back["wh_per_km"]) == (38, 180)
    assert back["usual_departure_local"] == "18:00"

    # At 50 m the garage is its own place, and only home to office repeats enough.
    assert [(r["start_location"], r["end_location"], r["drives"]) for r in tight] == [
        ("Commuter Home", "Commuter Office", 3)
    ]


async def test_routes_by_departure_hour_and_filters(mcp_session) -> None:
    async with mcp_session(seeds=["routes"]) as session:
        by_hour = await _rows(session, by_departure_hour=True)
        from_office = await _rows(session, start_location="office")
        busiest = await _rows(session, min_drives=4)
        one = await _rows(session, by_departure_hour=True, limit=1)

    assert [
        (r["end_location"], r["departure_hour"], r["drives"], r["typical_duration_min"])
        for r in by_hour
    ] == [
        ("Commuter Office", 8, 3, 34),
        ("Commuter Office", 9, 1, 32),
        ("Commuter Home", 18, 3, 38),
    ]
    assert [r["end_location"] for r in from_office] == ["Commuter Home"]
    assert [r["drives"] for r in busiest] == [4]
    # limit counts routes: the first route keeps both of its hours.
    assert [r["departure_hour"] for r in one] == [8, 9]
