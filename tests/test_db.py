"""Integration tests for the read-only execution helper (requires Docker)."""

from __future__ import annotations

import psycopg
import pytest

from teslamate_mcp.db import fetch_all, fetch_readonly


async def test_fetch_all_returns_jsonable_rows(pool) -> None:
    rows = await fetch_all(pool, "SELECT name, battery_kwh FROM demo_cars ORDER BY id")
    assert rows == [
        {"name": "Model 3", "battery_kwh": 75.0},
        {"name": "Model Y", "battery_kwh": 82.5},
    ]


async def test_fetch_readonly_returns_jsonable_rows(pool) -> None:
    rows = await fetch_readonly(
        pool,
        "SELECT name FROM demo_cars ORDER BY id",
        statement_timeout_ms=2000,
    )
    assert [r["name"] for r in rows] == ["Model 3", "Model Y"]


async def test_fetch_readonly_rejects_writes(pool) -> None:
    """A real READ ONLY transaction rejects INSERT at the PG layer."""
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        await fetch_readonly(
            pool,
            "INSERT INTO demo_cars (name) VALUES ('Cybertruck')",
            statement_timeout_ms=2000,
        )


async def test_fetch_readonly_enforces_statement_timeout(pool) -> None:
    """A slow query must be killed by statement_timeout."""
    with pytest.raises(psycopg.errors.QueryCanceled):
        await fetch_readonly(pool, "SELECT pg_sleep(2)", statement_timeout_ms=200)
