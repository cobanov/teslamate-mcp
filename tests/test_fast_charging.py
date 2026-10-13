"""Fast-charging tools against car 11 ("Sparky", conftest._FAST_SQL)."""

from __future__ import annotations

import re
from importlib.resources import files

_CAR = "Sparky"
_DC_TEST = "ch.fast_charger_present OR (ch.charger_phases IS NULL AND ch.charger_power > 0)"


async def _rows(session, tool: str, **args) -> list[dict]:
    result = await session.call_tool(tool, args)
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_fast_charging_sessions(mcp_session) -> None:
    async with mcp_session(seeds=["fast"]) as session:
        newest = await _rows(session, "get_fast_charging_sessions", car_name=_CAR)
        by_peak = await _rows(
            session, "get_fast_charging_sessions", car_name=_CAR, order_by="peak_power"
        )
        superchargers = await _rows(
            session, "get_fast_charging_sessions", car_name=_CAR, charger_type="supercharger"
        )

    # The AC session is not a fast-charging session, trailing 0 kW sample or not.
    assert [r["charging_process_id"] for r in newest] == [402, 401]
    assert [r["charging_process_id"] for r in by_peak] == [401, 402]
    assert [r["charging_process_id"] for r in superchargers] == [401]

    outlet, supercharger = newest
    assert (supercharger["charger_type"], supercharger["connector"]) == ("supercharger", "Combo")
    assert supercharger["peak_power_kw"] == 150
    assert supercharger["avg_power_kw"] == 60.0  # 76 kWh in 76 min
    assert supercharger["avg_power_20_80_kw"] == 127.1  # 31 samples at 150, 30 tapering
    assert supercharger["minutes_20_to_80"] == 60
    assert supercharger["battery_heater_on"] is False

    assert outlet["charger_type"] == "other_dc"
    assert outlet["avg_power_20_80_kw"] == 60.0
    assert outlet["minutes_20_to_80"] is None  # started at 30%
    assert outlet["battery_heater_on"] is True


async def test_fast_charging_by_location(mcp_session) -> None:
    async with mcp_session(seeds=["fast"]) as session:
        rows = await _rows(session, "get_fast_charging_by_location", car_name=_CAR)
        fastest = await _rows(
            session, "get_fast_charging_by_location", car_name=_CAR, order_by="avg_power_20_80"
        )

    assert [r["location"] for r in rows] == ["Outlet DC Charger", "Tesla Supercharger Gebze"]
    assert [r["location"] for r in fastest] == ["Tesla Supercharger Gebze", "Outlet DC Charger"]
    gebze = fastest[0]
    assert (gebze["sessions"], gebze["best_peak_power_kw"]) == (1, 150)
    assert gebze["avg_cost_per_kwh"] == 0.5
    assert fastest[1]["sessions_with_battery_heating"] == 1
    assert fastest[1]["avg_cost_per_kwh"] is None  # no costed session there


async def test_charging_curve_comparison(mcp_session) -> None:
    async with mcp_session(seeds=["fast"]) as session:
        latest = await _rows(session, "get_charging_curve_comparison", car_name=_CAR)
        named = await _rows(
            session, "get_charging_curve_comparison", charging_process_ids="401, 9999, x"
        )
        ac = await _rows(session, "get_charging_curve_comparison", charging_process_ids="403")

    assert {r["charging_process_id"] for r in latest} == {401, 402}
    assert (latest[0]["charging_process_id"], latest[0]["battery_level"]) == (402, 30)
    assert [r["battery_level"] for r in named] == list(range(10, 86))
    assert {r["charging_process_id"] for r in named} == {401}
    by_level = {r["battery_level"]: r["power_kw"] for r in named}
    assert (by_level[50], by_level[60], by_level[85]) == (150.0, 120.0, 45.0)
    # A named session is shown whatever its type; 0 kW samples are left out.
    assert {r["charger_type"] for r in ac} == {"ac"}
    assert [r["battery_level"] for r in ac] == list(range(40, 61))


async def test_trailing_zero_kw_sample_does_not_make_ac_count_as_dc(mcp_session) -> None:
    async with mcp_session(seeds=["fast"]) as session:
        rows = await _rows(session, "get_charging_efficiency", car_name=_CAR)
        estimates = await _rows(session, "get_charging_cost_estimates", car_name=_CAR)

    types = {r["charge_type"]: r["sessions"] for r in rows}
    assert types == {"AC": 1, "DC": 2}
    assert {r["charging_process_id"]: r["charger_type"] for r in estimates} == {
        403: "ac",
        402: "other_dc",
    }


def _sql(name: str) -> str:
    return files("teslamate_mcp").joinpath("queries", name).read_text(encoding="utf-8")


def test_dc_session_stats_block_is_shared() -> None:
    blocks = set()
    for name in ("fast_charging_sessions.sql", "fast_charging_by_location.sql"):
        match = re.search(
            r"-- dc session stats: begin.*?-- dc session stats: end", _sql(name), re.S
        )
        assert match, name
        blocks.add(match.group(0))
    assert len(blocks) == 1, "the dc session stats blocks have drifted apart"


def test_every_dc_classification_uses_the_same_test() -> None:
    for name in (
        "fast_charging_sessions.sql",
        "charging_cost_estimates.sql",
        "charging_curve_comparison.sql",
        "charging_efficiency.sql",
    ):
        assert _DC_TEST in " ".join(_sql(name).split()).replace("( ", "(").replace(" )", ")"), name
