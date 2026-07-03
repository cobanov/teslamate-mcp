"""Shared pytest fixtures. Integration tests require a Docker daemon."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio

# psycopg's async pool refuses to run on Windows' ProactorEventLoop. Forcing the
# selector policy at import time keeps the integration tests working both on
# Linux CI and on a developer's Windows box.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

try:  # pragma: no cover - import guarded so unit tests run without Docker
    from testcontainers.postgres import PostgresContainer

    _HAS_TESTCONTAINERS = True
except ImportError:  # pragma: no cover
    _HAS_TESTCONTAINERS = False

from mcp.shared.memory import create_connected_server_and_client_session

from teslamate_mcp.config import Settings
from teslamate_mcp.db import build_pool
from teslamate_mcp.server import create_server

# A miniature TeslaMate-shaped schema. Rolling-window rows are seeded relative
# to now() so CURRENT_DATE windows always match; one drive has a fixed UTC
# timestamp on a local-midnight boundary (22:30 UTC = 01:30 next day in
# Europe/Istanbul) to exercise REPORT_TIMEZONE bucketing.
_SETUP_SQL = """
DROP TABLE IF EXISTS demo_cars;
CREATE TABLE demo_cars (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    battery_kwh NUMERIC(6,2)
);
INSERT INTO demo_cars (name, battery_kwh) VALUES
    ('Model 3', 75.00),
    ('Model Y', 82.50);

DROP TABLE IF EXISTS charges, charging_processes, drives, positions, updates,
    addresses, car_settings, cars CASCADE;
CREATE TABLE car_settings (id BIGINT PRIMARY KEY, enabled BOOLEAN DEFAULT TRUE,
    free_supercharging BOOLEAN DEFAULT FALSE);
CREATE TABLE cars (id SMALLINT PRIMARY KEY, name TEXT, model TEXT, trim_badging TEXT,
    exterior_color TEXT, marketing_name TEXT, settings_id BIGINT REFERENCES car_settings(id));
CREATE TABLE addresses (id BIGINT PRIMARY KEY, display_name TEXT, city TEXT, state TEXT,
    latitude DOUBLE PRECISION, longitude DOUBLE PRECISION);
CREATE TABLE drives (id SERIAL PRIMARY KEY, car_id SMALLINT, start_date TIMESTAMP,
    end_date TIMESTAMP, distance DOUBLE PRECISION, duration_min SMALLINT, speed_max SMALLINT,
    power_max SMALLINT, power_min SMALLINT, start_km DOUBLE PRECISION, end_km DOUBLE PRECISION,
    inside_temp_avg DOUBLE PRECISION, outside_temp_avg DOUBLE PRECISION,
    start_address_id BIGINT, end_address_id BIGINT,
    start_rated_range_km DOUBLE PRECISION, end_rated_range_km DOUBLE PRECISION);
CREATE TABLE charging_processes (id SERIAL PRIMARY KEY, car_id SMALLINT, start_date TIMESTAMP,
    end_date TIMESTAMP, charge_energy_added DOUBLE PRECISION, duration_min INTEGER,
    cost NUMERIC(10,2), address_id BIGINT);
CREATE TABLE charges (id SERIAL PRIMARY KEY, charging_process_id INTEGER, date TIMESTAMP,
    battery_level SMALLINT, charger_power SMALLINT, charger_voltage INTEGER,
    charger_actual_current SMALLINT, rated_battery_range_km DOUBLE PRECISION,
    outside_temp DOUBLE PRECISION);
CREATE TABLE positions (id SERIAL PRIMARY KEY, car_id SMALLINT, date TIMESTAMP,
    latitude DOUBLE PRECISION, longitude DOUBLE PRECISION, battery_level SMALLINT,
    usable_battery_level SMALLINT, rated_battery_range_km DOUBLE PRECISION,
    ideal_battery_range_km DOUBLE PRECISION, est_battery_range_km DOUBLE PRECISION,
    odometer DOUBLE PRECISION, outside_temp DOUBLE PRECISION, is_climate_on BOOLEAN,
    tpms_pressure_fl DOUBLE PRECISION, tpms_pressure_fr DOUBLE PRECISION,
    tpms_pressure_rl DOUBLE PRECISION, tpms_pressure_rr DOUBLE PRECISION);
CREATE TABLE updates (id SERIAL PRIMARY KEY, car_id SMALLINT, version TEXT,
    start_date TIMESTAMP, end_date TIMESTAMP);

INSERT INTO car_settings (id) VALUES (1), (2);
INSERT INTO cars VALUES (1, 'Blue Thunder', 'model3', 'LR', 'DeepBlue', 'Model 3 LR', 1),
                        (2, 'Red Rocket', 'modely', 'P', 'Red', 'Model Y P', 2);
INSERT INTO addresses VALUES
    (1, 'Home Street 1', 'Istanbul', 'TR-34', 41.0, 29.0),
    (2, 'Office Plaza', 'Istanbul', 'TR-34', 41.1, 29.1),
    (3, 'Supercharger Edirne', 'Edirne', 'TR-22', 41.7, 26.6);
INSERT INTO drives (car_id, start_date, end_date, distance, duration_min, speed_max, power_max,
    power_min, start_km, end_km, inside_temp_avg, outside_temp_avg, start_address_id,
    end_address_id, start_rated_range_km, end_rated_range_km) VALUES
    (1, now() - interval '1 day', now() - interval '1 day' + interval '25 min',
     12.5, 25, 90, 120, -40, 1000.0, 1012.5, 22.0, 18.0, 1, 2, 400.0, 396.0),
    (1, now() - interval '2 days', now() - interval '2 days' + interval '95 min',
     120.0, 95, 140, 250, -60, 900.0, 1020.0, 21.5, 25.0, 2, 3, 380.0, 290.0),
    (2, now() - interval '1 day', now() - interval '1 day' + interval '10 min',
     5.0, 10, 60, 80, -20, 500.0, 505.0, 20.0, 15.0, 2, 1, 350.0, 348.0),
    (1, TIMESTAMP '2026-01-15 22:30:00', TIMESTAMP '2026-01-15 23:10:00',
     42.0, 40, 110, 150, -30, 800.0, 842.0, 21.0, 8.0, 1, 2, 420.0, 400.0);
INSERT INTO charging_processes (car_id, start_date, end_date, charge_energy_added,
    duration_min, cost, address_id) VALUES
    (1, now() - interval '1 day', now() - interval '1 day' + interval '30 min',
     30.0, 30, 12.50, 1),
    (1, now() - interval '10 days', now() - interval '10 days' + interval '40 min',
     50.0, 40, 30.00, 3),
    (2, now() - interval '3 days', now() - interval '3 days' + interval '60 min',
     20.0, 60, NULL, 1);
INSERT INTO charges (charging_process_id, date, battery_level, charger_power, charger_voltage,
    charger_actual_current, rated_battery_range_km, outside_temp)
SELECT 1, now() - interval '1 day' + (n || ' minutes')::interval,
       50 + n, 11, 230, 16, 300.0 + n, 15.0
FROM generate_series(0, 29) AS n;
INSERT INTO positions (car_id, date, latitude, longitude, battery_level, usable_battery_level,
    rated_battery_range_km, ideal_battery_range_km, est_battery_range_km, odometer, outside_temp,
    is_climate_on, tpms_pressure_fl, tpms_pressure_fr, tpms_pressure_rl, tpms_pressure_rr) VALUES
    (1, now() - interval '30 days', 41.0, 29.0, 100, 99, 420.0, 430.0, 415.0, 990.0, 12.0,
     FALSE, 2.9, 2.9, 2.8, 2.8),
    (1, now() - interval '1 hour', 41.05, 29.05, 80, 79, 330.0, 430.0, 320.0, 1012.5, 18.0,
     TRUE, 2.9, 3.0, 2.8, 2.9),
    (2, now() - interval '2 hours', 41.1, 29.1, 60, 59, 210.0, 350.0, 200.0, 505.0, 15.0,
     FALSE, 3.1, 3.1, 3.0, 3.0);
INSERT INTO updates (car_id, version, start_date, end_date) VALUES
    (1, '2026.20.1', now() - interval '5 days', now() - interval '5 days' + interval '25 min');
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
    except Exception as exc:
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


@pytest_asyncio.fixture
async def seeded_database(database_url) -> str:
    """Reset the seed data and hand back the connection URL for server tests."""
    settings = Settings(database_url=database_url)  # type: ignore[call-arg]
    pool = build_pool(settings)
    await pool.open()
    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(_SETUP_SQL)
    finally:
        await pool.close()
    return database_url


@pytest.fixture
def mcp_session(seeded_database):
    """Factory: an initialized in-memory MCP client session against a real server.

    Runs the full FastMCP stack (lifespan, pool, tool dispatch) without HTTP.
    Accepts Settings overrides, e.g. mcp_session(report_timezone="Europe/Istanbul").
    """

    @asynccontextmanager
    async def factory(**overrides):
        settings = Settings(database_url=seeded_database, **overrides)  # type: ignore[call-arg]
        mcp = create_server(settings)
        async with create_connected_server_and_client_session(
            mcp._mcp_server, raise_exceptions=False
        ) as session:
            yield session

    return factory
