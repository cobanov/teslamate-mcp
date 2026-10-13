"""get_unit_preferences: TeslaMate's display units, with safe fallbacks."""

from __future__ import annotations

import psycopg


async def _prefs(session) -> dict:
    result = await session.call_tool("get_unit_preferences", {})
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    (row,) = result.structured_content["result"]
    return row


async def test_unit_preferences_read_teslamate_settings(mcp_session) -> None:
    async with mcp_session() as session:
        prefs = await _prefs(session)
    assert prefs == {
        "unit_of_length": "mi",
        "unit_of_temperature": "F",
        "unit_of_pressure": "psi",
        "preferred_range": "ideal",
        "language": "en",
    }


async def test_unit_preferences_fall_back_to_teslamate_defaults(
    mcp_session, seeded_database
) -> None:
    # An older TeslaMate without unit_of_pressure, and then no settings row at all.
    async with await psycopg.AsyncConnection.connect(seeded_database, autocommit=True) as conn:
        await conn.execute("ALTER TABLE settings DROP COLUMN unit_of_pressure")
    async with mcp_session() as session:
        older = await _prefs(session)
        async with await psycopg.AsyncConnection.connect(seeded_database, autocommit=True) as conn:
            await conn.execute("DELETE FROM settings")
        empty = await _prefs(session)

    assert (older["unit_of_length"], older["unit_of_pressure"]) == ("mi", "bar")
    assert empty == {
        "unit_of_length": "km",
        "unit_of_temperature": "C",
        "unit_of_pressure": "bar",
        "preferred_range": "rated",
        "language": None,
    }
