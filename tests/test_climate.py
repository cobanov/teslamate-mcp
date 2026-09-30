"""Climate run while parked: get_parked_climate_sessions and get_climate_usage."""

from __future__ import annotations


async def _rows(session, tool: str, **args) -> list[dict]:
    result = await session.call_tool(tool, args)
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_parked_climate_sessions(mcp_session) -> None:
    async with mcp_session(seeds=["climate"]) as session:
        rows = await _rows(session, "get_parked_climate_sessions", car_name="chiller")
        long_only = await _rows(
            session, "get_parked_climate_sessions", car_name="chiller", min_minutes=7
        )

    got = [(r["kind"], r["mode"], r["minutes"], r["energy_kwh"], r["plugged_in"]) for r in rows]
    # Newest first; see conftest._CLIMATE_SQL for how each is built.
    assert got == [
        ("parked", "heating", 15, 0.0, True),
        ("before_drive", "heating", 10, 0.67, False),
        ("parked", "cooling", 20, 1.0, False),
        ("after_drive", "cooling", 6, 0.2, False),
    ]
    dog_mode = rows[2]
    assert (dog_mode["avg_power_kw"], dog_mode["outside_temp"], dog_mode["setpoint"]) == (
        3.0,
        30.0,
        22.0,
    )
    assert dog_mode["location"] == "Chiller Office"
    assert (rows[0]["location"], rows[1]["location"]) == ("Chiller Home", "Chiller Office")
    assert [r["minutes"] for r in long_only] == [15, 10, 20]


async def test_climate_usage(mcp_session) -> None:
    async with mcp_session(seeds=["climate"]) as session:
        rows = await _rows(session, "get_climate_usage", car_name="chiller", months=3)
        blips_excluded = await _rows(
            session, "get_climate_usage", car_name="chiller", months=3, min_minutes=12
        )

    assert len(rows) == 1  # every session is on the same day
    month = rows[0]
    assert (month["car_name"], month["sessions"], month["before_drive_sessions"]) == (
        "Chiller",
        4,
        1,
    )
    assert month["cooling_sessions"] == 2
    assert (month["hours"], month["plugged_in_hours"]) == (0.9, 0.3)  # 51 and 15 min
    assert month["energy_kwh"] == 1.9  # 0.2 + 1.0 + 0.67
    assert month["estimated_cost"] == 0.93  # at the month's 0.50 per kWh
    assert month["avg_outside_temp"] == 22.2  # time-weighted
    assert (blips_excluded[0]["sessions"], blips_excluded[0]["energy_kwh"]) == (2, 1.0)
