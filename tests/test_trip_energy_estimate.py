"""get_trip_energy_estimate against car 8 ("Planner", conftest._ESTIMATE_SQL).

City drives use 150 Wh/km at 20°C and 210 Wh/km at 0°C, motorway drives
180 Wh/km at 20°C; 1% of battery is 0.6 kWh (60 kWh usable).
"""

from __future__ import annotations

_CAR = "Planner"


async def _estimate(session, **args) -> dict:
    result = await session.call_tool("get_trip_energy_estimate", {"car_name": _CAR, **args})
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    (row,) = result.structured_content["result"]
    return row


async def test_estimate_uses_drives_at_a_similar_temperature(mcp_session) -> None:
    async with mcp_session(seeds=["estimate"]) as session:
        warm = await _estimate(session, distance_km=100, outside_temp_c=20)
        cold = await _estimate(session, distance_km=100, outside_temp_c=1)

    assert warm["based_on"] == "drives within 3°C"
    assert (warm["drives_used"], warm["km_used"]) == (10, 550)  # 5 city + 5 motorway
    assert warm["wh_per_km_expected"] == 177  # 97.5 kWh / 550 km
    assert warm["wh_per_km_conservative"] == 180
    assert warm["energy_needed_kwh"] == 17.7
    assert warm["usable_capacity_kwh"] == 60.0
    assert warm["full_battery_range_km"] == 338
    assert (warm["start_soc"], warm["soc_needed_pct"], warm["arrival_soc_pct"]) == (80, 29.5, 50.5)
    assert warm["start_soc_as_of"] is not None  # the latest recorded level

    assert (cold["based_on"], cold["drives_used"]) == ("drives within 3°C", 5)
    assert cold["wh_per_km_expected"] == 210


async def test_estimate_widens_the_temperature_window(mcp_session) -> None:
    async with mcp_session(seeds=["estimate"]) as session:
        mild = await _estimate(session, distance_km=100, outside_temp_c=10)
        any_temp = await _estimate(session, distance_km=100)

    # Nothing within 3 or 6°C of 10°C; both groups are exactly 10°C away.
    assert (mild["based_on"], mild["drives_used"]) == ("drives within 10°C", 15)
    assert (any_temp["based_on"], any_temp["drives_used"]) == ("drives at all temperatures", 15)


async def test_estimate_highway_and_start_soc(mcp_session) -> None:
    async with mcp_session(seeds=["estimate"]) as session:
        full = await _estimate(
            session, distance_km=300, outside_temp_c=20, highway=True, start_soc=100
        )
        now = await _estimate(session, distance_km=300, outside_temp_c=20, highway=True)

    assert full["drives_used"] == 5  # motorway drives only
    assert full["wh_per_km_expected"] == 180
    assert full["energy_needed_kwh"] == 54.0
    assert full["soc_needed_pct"] == 90.0
    assert (full["start_soc"], full["start_soc_as_of"]) == (100, None)
    assert full["arrival_soc_pct"] == 10.0
    assert now["arrival_soc_pct"] == -10.0  # from the recorded 80%: needs a charging stop
