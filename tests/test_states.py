"""State tools: get_state_history, get_idle_awake_periods, and car_state in
get_current_car_status (seeded cars 4-7, conftest._STATE_SQL).

Car 4 ("Night Owl") has fixed-shape days starting at UTC midnight two days
ago; cars 5-7 are driving, charging, and stale right now.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


async def _rows(session, tool: str, **args) -> list[dict]:
    result = await session.call_tool(tool, args)
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


def _utc_day(offset_days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=offset_days)).isoformat()


async def test_state_history_splits_states_by_day(mcp_session) -> None:
    async with mcp_session(seeds=["states"]) as session:
        rows = await _rows(session, "get_state_history", car_name="night owl", days=3)

    by_day = {r["day"]: r for r in rows}
    assert list(by_day) == [_utc_day(0), _utc_day(-1), _utc_day(-2)]  # newest first

    first = by_day[_utc_day(-2)]
    assert (first["online_hours"], first["asleep_hours"], first["offline_hours"]) == (
        2.5,
        21.5,
        0.0,
    )
    # The orphaned open drive inside this online period is not driving time.
    assert (first["driving_hours"], first["idle_awake_hours"]) == (0.0, 2.5)
    assert first["wakeups"] == 1
    assert first["pct_asleep_or_offline"] == 89.6

    second = by_day[_utc_day(-1)]
    assert (second["online_hours"], second["asleep_hours"], second["offline_hours"]) == (
        3.0,
        6.0,
        15.0,
    )
    assert (second["driving_hours"], second["charging_hours"]) == (0.5, 0.5)
    assert second["idle_awake_hours"] == 2.0  # 3 h online - 30 min drive - 30 min charge
    assert second["pct_asleep_or_offline"] == 87.5

    today = by_day[_utc_day(0)]
    assert today["online_hours"] == 0.0
    assert today["wakeups"] == 0


async def test_open_online_state_ends_at_last_position(mcp_session) -> None:
    async with mcp_session(seeds=["states"]) as session:
        rows = await _rows(session, "get_state_history", car_name="ghost", days=3)
        periods = await _rows(session, "get_idle_awake_periods", car_name="ghost")

    # Online "since two days ago", but nothing was logged after 01:00 that day.
    assert [(r["day"], r["online_hours"]) for r in rows] == [(_utc_day(-2), 1.0)]
    assert len(periods) == 1
    assert periods[0]["ongoing"] is True
    assert periods[0]["end_date"] is None
    assert periods[0]["idle_awake_hours"] == 1.0


async def test_idle_awake_periods_subtract_driving_and_charging(mcp_session) -> None:
    async with mcp_session(seeds=["states"]) as session:
        rows = await _rows(session, "get_idle_awake_periods", car_name="night owl")
        strict = await _rows(
            session, "get_idle_awake_periods", car_name="night owl", min_idle_minutes=150
        )

    assert [(r["online_hours"], r["idle_awake_hours"]) for r in rows] == [(2.5, 2.5), (3.0, 2.0)]
    night, morning = rows
    assert (night["drives_during"], night["charged_during"]) == (0, False)
    assert night["start_local"] == f"{_utc_day(-2)} 00:00"
    assert (morning["drives_during"], morning["charged_during"]) == (1, True)
    assert morning["location"] == "Office Plaza"  # where the drive inside it ended
    assert morning["ongoing"] is False
    assert [r["idle_awake_hours"] for r in strict] == [2.5]


async def test_current_car_state(mcp_session) -> None:
    async with mcp_session(seeds=["states"]) as session:
        rows = await _rows(session, "get_current_car_status")

    states = {r["car_name"]: r["car_state"] for r in rows}
    assert states["Night Owl"] == "asleep"
    assert states["Road Runner"] == "driving"
    assert states["Plug Star"] == "charging"
    # Its last position belongs to an open drive, but is two days old.
    assert states["Ghost Car"] == "online"
    assert states["Blue Thunder"] is None  # no state log at all

    night_owl = next(r for r in rows if r["car_name"] == "Night Owl")
    assert night_owl["car_state_since"] == f"{_utc_day(0)}T00:00:00"
