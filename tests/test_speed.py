"""get_efficiency_by_speed against car 13 ("Commuter", conftest._ROUTES_SQL)."""

from __future__ import annotations

_CAR = "Commuter"


async def _rows(session, **args) -> list[dict]:
    result = await session.call_tool("get_efficiency_by_speed", {"car_name": _CAR, **args})
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_efficiency_by_speed_bands(mcp_session) -> None:
    async with mcp_session(seeds=["routes"]) as session:
        rows = await _rows(session)
        wide = await _rows(session, band_kmh=30)

    assert [
        (r["speed_band"], r["speed_from_kmh"], r["distance_km"], r["wh_per_km"], r["vs_best_pct"])
        for r in rows
    ] == [
        ("50-60 km/h", 50, 25.0, 120, 0.0),
        # The drive's last sample has no next one to stand for: 59 half-minutes.
        ("120-130 km/h", 120, 59.0, 200, 66.7),
    ]
    assert (rows[0]["hours"], rows[0]["avg_outside_temp"]) == (0.5, 20.0)
    assert [r["speed_band"] for r in wide] == ["30-60 km/h", "120-150 km/h"]


async def test_efficiency_by_speed_temperature_filter(mcp_session) -> None:
    async with mcp_session(seeds=["routes"]) as session:
        mild = await _rows(session, outside_temp_c=22)
        freezing = await _rows(session, outside_temp_c=0)

    assert len(mild) == 2
    assert freezing == []  # the drive was at 20°C
