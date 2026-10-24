"""get_charging_time_estimate against car 11 ("Sparky", conftest._FAST_SQL).

Every session gains one battery percent a minute: the Supercharger from 10 to
85%, the third-party fast charger from 30 to 60%, the AC one from 40 to 60%.
"""

from __future__ import annotations

_CAR = "Sparky"


async def _rows(session, **args) -> list[dict]:
    result = await session.call_tool("get_charging_time_estimate", {"car_name": _CAR, **args})
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_charging_time_per_charger_type(mcp_session) -> None:
    async with mcp_session(seeds=["fast"]) as session:
        rows = await _rows(session, start_soc=20, target_soc=80)

    assert [r["charger_type"] for r in rows] == ["supercharger", "other_dc", "ac"]
    supercharger, other_dc, ac = rows
    # The same 60 minutes get_fast_charging_sessions reports as minutes_20_to_80.
    assert (supercharger["minutes"], supercharger["minutes_slow"]) == (60, 60)
    assert supercharger["energy_added_kwh"] == 60.8  # 76 kWh over 75 percent
    assert supercharger["avg_power_kw"] == 60.8
    assert supercharger["sessions_used"] == 1
    assert (supercharger["history_soc_from"], supercharger["history_soc_to"]) == (10, 85)

    # No history below 30% or above 60%: no time, but the band it does cover.
    assert (other_dc["minutes"], other_dc["avg_power_kw"]) == (None, None)
    assert (other_dc["history_soc_from"], other_dc["history_soc_to"]) == (30, 60)
    assert other_dc["energy_added_kwh"] == 50.0
    # The trailing 0 kW sample at 60% is not charging time.
    assert (ac["history_soc_from"], ac["history_soc_to"]) == (40, 60)


async def test_charging_time_filters_and_bounds(mcp_session) -> None:
    async with mcp_session(seeds=["fast"]) as session:
        covered = await _rows(session, start_soc=30, target_soc=60, charger_type="other_dc")
        dc = await _rows(session, start_soc=40, target_soc=60, charger_type="dc")
        gebze = await _rows(session, start_soc=40, target_soc=60, location="gebze")
        done = await _rows(session, start_soc=90, target_soc=80, charger_type="supercharger")
        unknown = await _rows(session, charger_type="supercharger")

    (row,) = covered
    assert (row["minutes"], row["energy_added_kwh"], row["avg_power_kw"]) == (30, 25.0, 50.0)
    assert [r["charger_type"] for r in dc] == ["supercharger", "other_dc"]
    assert [r["minutes"] for r in dc] == [20, 20]
    assert [r["charger_type"] for r in gebze] == ["supercharger"]
    assert (done[0]["minutes"], done[0]["energy_added_kwh"]) == (0, 0.0)
    # Sparky has no recorded battery level to start from.
    assert (unknown[0]["start_soc"], unknown[0]["minutes"]) == (None, None)
