"""Costs, hours, regions, odometer, range, style, consumption and drive energy
against car 17 ("Insight", conftest._INSIGHTS_SQL)."""

from __future__ import annotations

from datetime import UTC, datetime

_CAR = "Insight"


def _months() -> tuple[str, str]:
    """The seed's base month (last month) and the month of D0 and C0, 30 days earlier."""
    now = datetime.now(UTC)
    year, month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    base = datetime(year, month, 10, tzinfo=UTC)
    earlier = base.toordinal() - 30 + 10 / 24  # D0 starts at 10:00
    early = datetime.fromordinal(int(earlier))
    return f"{year:04d}-{month:02d}", f"{early.year:04d}-{early.month:02d}"


async def _rows(session, tool: str, **args) -> list[dict]:
    result = await session.call_tool(tool, args)
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_cost_per_distance_splits_ac_and_dc(mcp_session) -> None:
    base_month, early_month = _months()
    async with mcp_session(seeds=["insights"]) as session:
        rows = await _rows(session, "get_cost_per_distance", car_name=_CAR)

    assert [r["month"] for r in rows] == [base_month, early_month]
    month = rows[0]
    assert (month["distance_km"], month["sessions"], month["sessions_without_cost"]) == (
        160.0,
        3,
        1,
    )
    assert (month["energy_added_kwh"], month["ac_kwh"], month["dc_kwh"]) == (80.0, 50.0, 30.0)
    assert month["cost"] == 16.0
    # AC: 4.00 for 40 kWh (the unpriced 10 kWh session is left out); DC: 12.00 for 30.
    assert (month["ac_cost_per_kwh"], month["dc_cost_per_kwh"]) == (0.1, 0.4)
    assert month["cost_per_kwh"] == 0.229
    assert (month["cost_per_100km"], month["kwh_charged_per_100km"]) == (10.0, 50.0)
    assert (rows[1]["distance_km"], rows[1]["cost_per_100km"]) == (20.0, 10.0)


async def test_charging_hours(mcp_session) -> None:
    async with mcp_session(seeds=["insights"]) as session:
        rows = await _rows(session, "get_charging_hours", car_name=_CAR)

    assert [(r["start_hour"], r["sessions"], r["ac_sessions"], r["dc_sessions"]) for r in rows] == [
        (12, 2, 1, 1),  # C0 (AC) and C2 (DC)
        (22, 2, 2, 0),
    ]
    assert [r["energy_added_kwh"] for r in rows] == [50.0, 50.0]
    assert [r["share_of_energy_pct"] for r in rows] == [50.0, 50.0]
    assert rows[1]["avg_start_level"] == 50  # 30 % and 70 %


async def test_driving_hours_grid(mcp_session) -> None:
    async with mcp_session(seeds=["insights"]) as session:
        rows = await _rows(session, "get_driving_hours", car_name=_CAR)

    # Seven drives: three mornings and three evenings in a row, and D0 at 10:00.
    assert sorted(r["start_hour"] for r in rows) == [8, 8, 8, 10, 18, 18, 18]
    assert all(r["drives"] == 1 for r in rows)
    assert {r["weekday"] for r in rows if r["start_hour"] == 8} == {
        r["weekday"] for r in rows if r["start_hour"] == 18
    }
    assert all(1 <= r["weekday"] <= 7 and r["weekday_name"] for r in rows)
    assert sum(r["distance_km"] for r in rows) == 180.0
    assert sum(r["driving_hours"] for r in rows) == 3.5


async def test_regions_visited_roll_up(mcp_session) -> None:
    async with mcp_session(seeds=["insights"]) as session:
        cities = await _rows(session, "get_regions_visited", car_name=_CAR)
        countries = await _rows(session, "get_regions_visited", car_name=_CAR, level="country")
        states = await _rows(session, "get_regions_visited", car_name=_CAR, level="state")

    assert [(r["city"], r["arrivals"], r["charging_sessions"]) for r in cities] == [
        ("Kadikoy", 3, 2),
        ("Besiktas", 3, 1),
        ("Volos", 1, 1),
    ]
    assert [
        (r["country"], r["state"], r["city"], r["places"], r["arrivals"]) for r in countries
    ] == [
        ("Turkey", None, None, 2, 6),
        ("Greece", None, None, 1, 1),
    ]
    assert [(r["state"], r["city"]) for r in states] == [("Istanbul", None), ("Thessaly", None)]
    assert all(r["first_visit"] <= r["last_visit"] for r in cities)


async def test_odometer_history(mcp_session) -> None:
    base_month, early_month = _months()
    async with mcp_session(seeds=["insights"]) as session:
        rows = await _rows(session, "get_odometer_history", car_name=_CAR)

    assert [
        (
            r["month"],
            r["odometer_start_km"],
            r["odometer_end_km"],
            r["distance_km"],
            r["drives"],
            r["days_driven"],
        )
        for r in rows
    ] == [
        (early_month, 5000, 5020, 20.0, 1, 1),
        (base_month, 10000, 10160, 160.0, 6, 3),
    ]


async def test_projected_range_by_mileage(mcp_session) -> None:
    async with mcp_session(seeds=["insights"]) as session:
        rows = await _rows(session, "get_projected_range_by_mileage", car_name=_CAR)
        wide = await _rows(
            session, "get_projected_range_by_mileage", car_name=_CAR, bucket_km=10000
        )

    # C0 follows D0 (odometer 5020); C1-C3 follow D4-D6 (10120-10160).
    assert [
        (r["odometer_from_km"], r["odometer_to_km"], r["charges"], r["range_at_100_km"])
        for r in rows
    ] == [(5000, 6000, 1, 520.0), (10000, 11000, 3, 500.0)]
    assert [r["vs_best_pct"] for r in rows] == [0.0, -3.8]
    assert [(r["odometer_from_km"], r["charges"]) for r in wide] == [(0, 1), (10000, 3)]


async def test_battery_summary_capacity_and_cycles(mcp_session) -> None:
    async with mcp_session(seeds=["insights"]) as session:
        row = (await _rows(session, "get_battery_health_summary", car_name=_CAR))[0]

    # Newest charges ending at 50 % or more: 500, 500, 500, 520 km at 100 %.
    assert row["range_at_100_km"] == 500.0
    # C1 gained 50 points for 40 kWh (80 kWh), C2 40 points for 30 kWh (75 kWh).
    assert (row["est_capacity_kwh"], row["capacity_sessions"]) == (77.5, 2)
    assert (row["ac_energy_added_kwh"], row["dc_energy_added_kwh"]) == (70.0, 30.0)
    assert row["charge_cycles"] == 1.3  # 100 kWh / 77.5 kWh


async def test_drive_details_energy_from_power_samples(mcp_session) -> None:
    async with mcp_session(seeds=["insights"]) as session:
        d1 = (await _rows(session, "get_drive_details", drive_id=1701))[0]
        d2 = (await _rows(session, "get_drive_details", drive_id=1702))[0]

    # 360 five-second samples: 12 at 100 kW and 342 at 15 kW drive the car,
    # 6 at -60 kW recover energy; the last sample has no next one.
    assert (d1["energy_used_kwh"], d1["energy_recovered_kwh"], d1["regen_share_pct"]) == (
        8.79,
        0.5,
        5.7,
    )
    assert (d2["energy_used_kwh"], d2["energy_recovered_kwh"], d2["regen_share_pct"]) == (
        None,
        None,
        None,
    )


async def test_search_drives_against_expected_consumption(mcp_session) -> None:
    async with mcp_session(seeds=["insights"]) as session:
        rows = await _rows(session, "search_drives", car_name=_CAR)

    by_id = {r["drive_id"]: r for r in rows}
    # D3 at 21 °C against D1, D2, D4, D5 (19-22 °C): 150, 150, 150, 165 -> 150.
    d3 = by_id[1703]
    assert (d3["wh_per_km"], d3["expected_wh_per_km"], d3["vs_expected_pct"]) == (180, 150, 20.0)
    assert d3["expected_basis_drives"] == 4
    # D1 against 150, 150, 165, 180: the median is 157.5.
    assert (by_id[1701]["expected_wh_per_km"], by_id[1701]["vs_expected_pct"]) == (158, -4.8)
    # Nothing else was driven near 0 °C or 10 °C.
    assert by_id[1706]["wh_per_km"] == 180
    assert by_id[1706]["expected_wh_per_km"] is None
    assert by_id[1700]["vs_expected_pct"] is None


async def test_driving_style_events_and_score(mcp_session) -> None:
    base_month, _ = _months()
    async with mcp_session(seeds=["insights"]) as session:
        rows = await _rows(session, "get_driving_style", car_name=_CAR)
        strict = await _rows(session, "get_driving_style", car_name=_CAR, fast_kmh=140)
        gentle = await _rows(session, "get_driving_style", car_name=_CAR, accel_kw=101)

    # D0's month has no samples, so only the base month is rated.
    assert [r["month"] for r in rows] == [base_month]
    row = rows[0]
    assert (row["drives"], row["distance_km"], row["moving_hours"]) == (6, 160.0, 0.5)
    # Two runs at 100 kW and one at -60 kW over 160 km.
    assert (row["hard_accel_per_100km"], row["hard_regen_per_100km"]) == (1.3, 0.6)
    assert row["over_fast_pct"] == 16.7  # 300 s of 1800 s at 130 km/h
    assert (row["max_speed_kmh"], row["regen_share_pct"]) == (130, 5.7)
    assert row["style_score"] == 91  # 100 - 0.63 - 0.16 - 8.33
    assert (strict[0]["over_fast_pct"], strict[0]["style_score"]) == (0.0, 99)
    # Nothing reached 101 kW.
    assert (gentle[0]["hard_accel_per_100km"], gentle[0]["style_score"]) == (0.0, 92)


def _decode(paths: str) -> list[list[tuple[float, float]]]:
    """The view's decoding of get_driven_roads' paths."""
    drives = []
    for drive in paths.split(";"):
        x = y = 0
        points = []
        for i, pair in enumerate(drive.split(" ")):
            dx, dy = (int(v) for v in pair.split(","))
            x, y = (x + dx, y + dy) if i else (dx, dy)
            points.append((x / 10000, y / 10000))
        drives.append(points)
    return drives


async def test_driven_roads_paths(mcp_session) -> None:
    async with mcp_session(seeds=["insights"]) as session:
        rows = await _rows(session, "get_driven_roads", car_name=_CAR)
        thin = await _rows(session, "get_driven_roads", car_name=_CAR, max_points=200)
        long_only = await _rows(session, "get_driven_roads", car_name=_CAR, min_distance_km=40)

    # Only D1 has GPS samples.
    row = rows[0]
    assert (row["car_name"], row["routes"], row["points"], row["distance_km"]) == (
        _CAR,
        1,
        361,
        30.0,
    )
    (path,) = _decode(row["paths"])
    assert len(path) == 361
    # Longitude first, GeoJSON order; the samples step 0.0001° each way.
    assert (path[0], path[1], path[-1]) == ((29.03, 41.0), (29.0299, 41.0001), (28.994, 41.036))
    assert row["first_drive"] == row["last_drive"]
    (thin_path,) = _decode(thin[0]["paths"])
    assert len(thin_path) == thin[0]["points"] < 200
    assert long_only == []
