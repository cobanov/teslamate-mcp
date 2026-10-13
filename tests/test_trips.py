"""Trip tools: get_trips, get_trip_details, get_trip_route (seeded car-3 road trip).

The seed (conftest._TRIP_SQL) is one Istanbul -> Ankara trip of drives 101-103
with a 20-min WC stop and a 70-min stop around a 40-min charge, an overnight
stop with a hotel charge, then drives 104 and 105 split by a 45-min stop.
"""

from __future__ import annotations

import re
from importlib.resources import files

_CAR = "Road Tripper"


async def _rows(session, tool: str, **args) -> list[dict]:
    result = await session.call_tool(tool, args)
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_trips_merge_short_and_charging_stops(mcp_session) -> None:
    async with mcp_session(with_trips=True) as session:
        trips = await _rows(session, "get_trips", car_name=_CAR)

    assert [t["trip_id"] for t in trips] == [105, 104, 101]  # newest first
    road = trips[2]
    assert road["legs"] == 3
    assert road["stops"] == 2
    assert road["charging_stops"] == 1
    assert road["distance_km"] == 360.0
    assert road["driving_min"] == 230
    assert road["total_min"] == 320  # 06:00 -> 11:20
    assert road["stopped_min"] == 90  # 20-min WC + 70-min charging stop
    assert road["avg_moving_speed_kmh"] == 93.9
    assert road["speed_max_kmh"] == 130
    assert (road["start_location"], road["start_city"]) == ("Home Street 1", "Istanbul")
    assert (road["end_location"], road["end_city"]) == ("Kizilay Square", "Ankara")
    assert road["energy_added_kwh"] == 35.0  # the hotel charge is outside the trip
    assert road["rated_range_used_km"] == 285.0  # driving only; the charge adds range back
    assert (road["start_battery_level"], road["end_battery_level"]) == (90, 60)
    assert road["outside_temp_avg"] == 22.8  # weighted by driving minutes


async def test_stop_limits_decide_where_trips_split(mcp_session) -> None:
    async with mcp_session(with_trips=True) as session:
        # A 60-min plain-stop limit absorbs the 45-min stop between 104 and 105.
        longer = await _rows(session, "get_trips", car_name=_CAR, max_stop_minutes=60)
        # A 60-min charging-stop limit no longer covers the 70-min charging stop.
        shorter = await _rows(session, "get_trips", car_name=_CAR, max_charging_stop_minutes=60)

    assert [(t["trip_id"], t["legs"]) for t in longer] == [(104, 2), (101, 3)]
    assert longer[0]["charging_stops"] == 0
    assert [(t["trip_id"], t["legs"]) for t in shorter] == [(105, 1), (104, 1), (103, 1), (101, 2)]


async def test_trip_filters(mcp_session) -> None:
    async with mcp_session(with_trips=True) as session:
        via_bolu = await _rows(session, "get_trips", car_name=_CAR, location="bolu")
        multi_leg = await _rows(session, "get_trips", car_name=_CAR, min_legs=2)
        second_day = await _rows(session, "get_trips", car_name=_CAR, start_date="2025-06-11")
        longest = await _rows(session, "get_trips", car_name=_CAR, order_by="distance", limit=1)
        long_only = await _rows(session, "get_trips", car_name=_CAR, min_distance_km=100)

    # Bolu is only a stop on the way, never an endpoint.
    assert [t["trip_id"] for t in via_bolu] == [101]
    assert [t["trip_id"] for t in multi_leg] == [101]
    assert [t["trip_id"] for t in second_day] == [105, 104]
    assert [t["trip_id"] for t in longest] == [101]
    assert [t["trip_id"] for t in long_only] == [101]


async def test_trip_details_timeline(mcp_session) -> None:
    async with mcp_session(with_trips=True) as session:
        rows = await _rows(session, "get_trip_details", trip_id=101)
        # Any drive of the trip resolves to the same trip.
        from_middle = await _rows(session, "get_trip_details", trip_id=102)
        single = await _rows(session, "get_trip_details", trip_id=104)

    assert [(r["seq"], r["kind"], r["leg"], r["drive_id"]) for r in rows] == [
        (1, "drive", 1, 101),
        (2, "stop", 1, None),
        (3, "drive", 2, 102),
        (4, "charging_stop", 2, None),
        (5, "drive", 3, 103),
    ]
    assert {r["trip_id"] for r in rows} == {101}
    wc, charge = rows[1], rows[3]
    assert wc["duration_min"] == 20
    assert wc["from_location"] == "Bolu Rest Area"
    assert wc["charge_energy_added_kwh"] is None
    assert charge["duration_min"] == 70
    assert charge["from_location"] == "Supercharger Bolu"
    assert charge["charge_energy_added_kwh"] == 35.0
    assert (charge["charge_start_battery_level"], charge["charge_end_battery_level"]) == (30, 75)
    assert rows[0]["distance_km"] == 140.0
    assert (rows[4]["from_location"], rows[4]["to_city"]) == ("Supercharger Bolu", "Ankara")

    assert from_middle == rows
    assert [(r["kind"], r["drive_id"]) for r in single] == [("drive", 104)]


async def test_trip_route_spans_all_legs(mcp_session) -> None:
    async with mcp_session(with_trips=True) as session:
        points = await _rows(session, "get_trip_route", trip_id=101)
        capped = await _rows(session, "get_trip_route", trip_id=101, max_points=10)

    assert len(points) == 12  # 4 seeded positions per leg
    assert [p["point_order"] for p in points] == list(range(1, 13))
    assert [p["ts"] for p in points] == sorted(p["ts"] for p in points)
    first_of_leg = {p["leg"]: p for p in reversed(points)}
    assert [first_of_leg[leg]["stop_before"] for leg in (1, 2, 3)] == [
        "start",
        "stop",
        "charging_stop",
    ]
    assert [first_of_leg[leg]["stop_before_min"] for leg in (1, 2, 3)] == [None, 20, 70]
    assert {p["drive_id"] for p in points} == {101, 102, 103}
    # Buckets split at stops, so a cap can be exceeded by at most legs - 1.
    assert len(capped) <= 10 + 2
    assert {p["leg"] for p in capped} == {1, 2, 3}


def _grouping_block(sql_file: str) -> str:
    sql = files("teslamate_mcp").joinpath("queries", sql_file).read_text(encoding="utf-8")
    match = re.search(r"-- trip grouping: begin.*?-- trip grouping: end", sql, re.S)
    assert match, sql_file
    return match.group(0)


def test_trip_grouping_is_identical_in_every_trip_query() -> None:
    """get_trips, get_trip_details and get_trip_route must agree on what a trip is."""
    blocks = {f: _grouping_block(f) for f in ("trips.sql", "trip_details.sql", "trip_route.sql")}
    assert len(set(blocks.values())) == 1, "trip grouping blocks have drifted apart"
