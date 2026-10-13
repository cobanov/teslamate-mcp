"""Cost tools: get_charging_cost_estimates and get_fuel_savings (conftest._COST_SQL)."""

from __future__ import annotations


async def _rows(session, tool: str, **args) -> list[dict]:
    result = await session.call_tool(tool, args)
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_cost_estimates_pick_the_first_basis_that_applies(mcp_session) -> None:
    async with mcp_session(seeds=["costs"]) as session:
        rows = await _rows(session, "get_charging_cost_estimates")

    by_id = {r["charging_process_id"]: r for r in rows}
    # Newest first; session 307 added nothing and is skipped.
    assert list(by_id) == [3, 306, 305, 304, 303]

    home = by_id[3]  # Red Rocket at the "Home" geofence, 0.28 per kWh
    assert (home["estimated_cost"], home["basis"]) == (5.88, "geofence Home tariff per kWh")
    assert home["energy_billed_kwh"] == 21.0  # kWh drawn, the larger of the two

    assert (by_id[306]["estimated_cost"], by_id[306]["basis"]) == (0.0, "free Supercharging")

    supercharger = by_id[303]  # median of 0.50 and 0.60 paid at the same address
    assert supercharger["charger_type"] == "supercharger"
    assert (supercharger["price_per_kwh"], supercharger["estimated_cost"]) == (0.55, 16.5)
    assert supercharger["basis"] == "median price at this location (n=2)"

    mall = by_id[304]  # a new place: the third-party DC price from the base seed
    assert (mall["charger_type"], mall["estimated_cost"]) == ("other_dc", 11.11)
    assert mall["basis"] == "median other dc price (n=1)"

    garage = by_id[305]  # a new place: the AC price from the base seed
    assert (garage["charger_type"], garage["estimated_cost"]) == ("ac", 4.17)


async def test_cost_estimates_with_a_given_price(mcp_session) -> None:
    async with mcp_session(seeds=["costs"]) as session:
        ac = await _rows(
            session,
            "get_charging_cost_estimates",
            charger_type="ac",
            price_per_kwh=0.40,
            session_fee=1.0,
        )
        superchargers = await _rows(
            session, "get_charging_cost_estimates", charger_type="supercharger", price_per_kwh=0.40
        )
        dc = await _rows(session, "get_charging_cost_estimates", charger_type="dc")

    assert [(r["charging_process_id"], r["estimated_cost"]) for r in ac] == [(3, 9.4), (305, 5.4)]
    assert {r["basis"] for r in ac} == {"price_per_kwh argument"}
    # Free Supercharging still wins over a given price.
    assert [(r["charging_process_id"], r["estimated_cost"]) for r in superchargers] == [
        (306, 0.0),
        (303, 12.0),
    ]
    assert [r["charging_process_id"] for r in dc] == [306, 304, 303]


async def test_fuel_savings(mcp_session) -> None:
    args = {"fuel_price_per_liter": 5.0, "fuel_consumption_l_per_100km": 8.0, "days": 30}
    async with mcp_session() as session:
        rows = await _rows(session, "get_fuel_savings", **args)
        priced = await _rows(
            session, "get_fuel_savings", car_name="red", electricity_price_per_kwh=0.30, **args
        )

    blue = next(r for r in rows if r["car_name"] == "Blue Thunder")
    assert blue["distance_km"] == 132.5  # 12.5 + 120 km in the last 30 days
    assert (blue["fuel_liters"], blue["fuel_cost"]) == (10.6, 53.0)
    assert (blue["charging_sessions"], blue["kwh_added"]) == (2, 80.0)
    assert (blue["electricity_cost"], blue["cost_coverage_pct"]) == (42.5, 100.0)
    assert blue["savings"] == 10.5
    assert (blue["electricity_cost_per_100km"], blue["fuel_cost_per_100km"]) == (32.08, 40.0)

    red = next(r for r in rows if r["car_name"] == "Red Rocket")
    # Its only session has no cost: the electricity cost is incomplete, not zero.
    assert (red["sessions_without_cost"], red["cost_coverage_pct"]) == (1, 0.0)
    assert red["estimated_missing_cost"] is None

    (red_priced,) = priced
    assert red_priced["estimated_missing_cost"] == 6.3  # 21 kWh drawn x 0.30
    assert (red_priced["electricity_cost"], red_priced["cost_coverage_pct"]) == (6.3, 100.0)
    assert red_priced["savings"] == -4.3  # 5 km of fuel costs 2.00
