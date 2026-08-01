"""Integration tests for the read-only execution helper (requires Docker)."""

from __future__ import annotations

import psycopg
import pytest

from teslamate_mcp.config import Settings
from teslamate_mcp.db import build_pool, fetch_all, fetch_readonly


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


async def test_predefined_path_is_bounded_by_the_pool_timeout(pool) -> None:
    """fetch_all sets no timeout of its own; the pool's connection option is the bound.

    Regression: two bundled reports used a correlated subquery that never
    completed. With no timeout anywhere on this path the MCP call hung
    forever, and killing the client left the backend burning CPU server-side.
    """
    with pytest.raises(psycopg.errors.QueryCanceled):
        await fetch_all(pool, "SELECT pg_sleep(60)")


def test_build_pool_sets_a_statement_timeout() -> None:
    settings = Settings(  # type: ignore[call-arg]
        database_url="postgresql://u:p@localhost:5432/db",
        statement_timeout_ms=12345,
    )
    assert build_pool(settings).kwargs["options"] == "-c statement_timeout=12345"


def test_build_pool_defers_to_operator_supplied_options() -> None:
    """An explicit libpq options= in DATABASE_URL must not be clobbered."""
    settings = Settings(  # type: ignore[call-arg]
        database_url="postgresql://u:p@localhost:5432/db?options=-c%20statement_timeout%3D999",
    )
    assert "options" not in build_pool(settings).kwargs
