"""Shared pytest fixtures. Integration tests require a Docker daemon."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

try:  # pragma: no cover - import guarded so unit tests run without Docker
    from testcontainers.postgres import PostgresContainer

    _HAS_TESTCONTAINERS = True
except ImportError:  # pragma: no cover
    _HAS_TESTCONTAINERS = False

from teslamate_mcp.db import build_pool
from teslamate_mcp.config import Settings


_SETUP_SQL = """
CREATE TABLE IF NOT EXISTS demo_cars (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    battery_kwh NUMERIC(6,2)
);
INSERT INTO demo_cars (name, battery_kwh) VALUES
    ('Model 3', 75.00),
    ('Model Y', 82.50);
"""


@pytest.fixture(scope="session")
def postgres_container():
    """Start a single Postgres container for the test session.

    Returns the container instance, or skips all integration tests when Docker
    is unavailable. Sharing one container across the session keeps test
    startup time bounded.
    """
    if not _HAS_TESTCONTAINERS:
        pytest.skip("testcontainers is not installed")
    try:
        container = PostgresContainer("postgres:16-alpine")
        container.start()
    except Exception as exc:  # noqa: BLE001 — broad on purpose, any docker issue → skip
        pytest.skip(f"Docker is not available: {exc}")
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def database_url(postgres_container) -> str:
    return postgres_container.get_connection_url().replace(
        "postgresql+psycopg2://", "postgresql://"
    )


@pytest_asyncio.fixture
async def pool(database_url) -> AsyncIterator:
    """A fresh psycopg pool per test, with the demo schema bootstrapped."""
    settings = Settings(database_url=database_url)  # type: ignore[call-arg]
    pool = build_pool(settings)
    await pool.open()
    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(_SETUP_SQL)
        yield pool
    finally:
        await pool.close()
