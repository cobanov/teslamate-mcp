"""get_health_checks against car 18 ("Medic", conftest._MEDIC_SQL)."""

from __future__ import annotations

import psycopg


async def _checks(session, **args) -> list[dict]:
    result = await session.call_tool("get_health_checks", args)
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_health_checks_worst_first(mcp_session) -> None:
    async with mcp_session(seeds=["medic"]) as session:
        rows = await _checks(session, car_name="medic")

    assert [(r["check_name"], r["status"], r["value"], r["unit"]) for r in rows] == [
        ("parked_drain", "alert", 12.0, "km/day"),
        ("tire_pressure", "alert", 0.4, "bar"),
        ("battery_level", "warn", 15, "%"),
        ("full_charge_sits", "warn", 2, "charges"),
        # 29 h online, minus two 30-minute drives and a 1-hour charge, over 7 days.
        ("idle_awake", "warn", 3.9, "h/day"),
        ("open_records", "warn", 1, "rows"),
        ("range_loss", "warn", 12.0, "%"),
        ("last_data", "ok", 0.0, "days"),
    ]
    detail = {r["check_name"]: r["detail"] for r in rows}
    assert "FL 2.50, FR 2.90" in detail["tire_pressure"]
    assert "FL -0.40, FR 0.00" in detail["tire_pressure"]
    assert detail["open_records"].startswith("1 drives and 0 charges")
    assert "440.0 km now" in detail["range_loss"] and "500.0 km" in detail["range_loss"]
    assert "2 of 2 charges to 95 % or more" in detail["full_charge_sits"]
    assert "online since" in detail["last_data"]


async def test_health_checks_without_data(mcp_session) -> None:
    """The base cars have a little of everything and none of the history."""
    async with mcp_session() as session:
        rows = await _checks(session, car_name="red rocket")

    status = {r["check_name"]: r["status"] for r in rows}
    assert len(rows) == 8
    assert (status["range_loss"], status["parked_drain"]) == ("unknown", "unknown")
    assert status["battery_level"] == "ok"
    assert rows[0]["status"] in {"alert", "warn", "unknown"}


async def test_tire_pressure_with_a_missing_sensor_is_unknown(mcp_session, seeded_database) -> None:
    """Three readings cannot produce a spread, so the check must not read as OK."""
    async with mcp_session(seeds=["medic"]) as session:
        async with await psycopg.AsyncConnection.connect(seeded_database, autocommit=True) as conn:
            await conn.execute(
                """
                UPDATE positions
                SET tpms_pressure_fr = NULL,
                    tpms_pressure_rl = NULL,
                    tpms_pressure_rr = NULL
                WHERE car_id = 18
                  AND date > now() - interval '7 days'
                """
            )
        rows = await _checks(session, car_name="medic")

    tire = next(r for r in rows if r["check_name"] == "tire_pressure")
    assert tire["status"] == "unknown"
    assert tire["value"] is None
    assert "incomplete" in tire["detail"]
