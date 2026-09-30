"""Shared pytest fixtures.

Integration tests need PostgreSQL: a Docker daemon (testcontainers), or an
existing server named by TESLAMATE_TEST_DATABASE_URL. The seed SQL drops and
recreates its tables, so point that at a scratch database, never TeslaMate's.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
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

from mcp import Client

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

DROP TABLE IF EXISTS charges, charging_processes, drives, positions, updates, states,
    settings, addresses, geofences, car_settings, cars CASCADE;
CREATE TABLE car_settings (id BIGINT PRIMARY KEY, enabled BOOLEAN DEFAULT TRUE,
    free_supercharging BOOLEAN DEFAULT FALSE);
CREATE TABLE cars (id SMALLINT PRIMARY KEY, name TEXT, model TEXT, trim_badging TEXT,
    exterior_color TEXT, marketing_name TEXT, settings_id BIGINT REFERENCES car_settings(id),
    efficiency DOUBLE PRECISION);
CREATE TABLE addresses (id BIGINT PRIMARY KEY, display_name TEXT, city TEXT, state TEXT,
    latitude DOUBLE PRECISION, longitude DOUBLE PRECISION);
CREATE TABLE geofences (id BIGINT PRIMARY KEY, name TEXT, latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION, radius SMALLINT, cost_per_unit NUMERIC,
    session_fee NUMERIC, billing_type TEXT);
CREATE TABLE drives (id SERIAL PRIMARY KEY, car_id SMALLINT, start_date TIMESTAMP,
    end_date TIMESTAMP, distance DOUBLE PRECISION, duration_min SMALLINT, speed_max SMALLINT,
    power_max SMALLINT, power_min SMALLINT, start_km DOUBLE PRECISION, end_km DOUBLE PRECISION,
    inside_temp_avg DOUBLE PRECISION, outside_temp_avg DOUBLE PRECISION,
    start_address_id BIGINT, end_address_id BIGINT,
    start_rated_range_km DOUBLE PRECISION, end_rated_range_km DOUBLE PRECISION,
    start_position_id INTEGER, end_position_id INTEGER,
    start_geofence_id BIGINT, end_geofence_id BIGINT, ascent SMALLINT, descent SMALLINT);
CREATE TABLE charging_processes (id SERIAL PRIMARY KEY, car_id SMALLINT, start_date TIMESTAMP,
    end_date TIMESTAMP, charge_energy_added DOUBLE PRECISION, duration_min INTEGER,
    cost NUMERIC(10,2), address_id BIGINT, geofence_id BIGINT,
    start_battery_level SMALLINT, end_battery_level SMALLINT,
    charge_energy_used DOUBLE PRECISION,
    start_rated_range_km DOUBLE PRECISION, end_rated_range_km DOUBLE PRECISION,
    outside_temp_avg DOUBLE PRECISION);
CREATE TABLE charges (id SERIAL PRIMARY KEY, charging_process_id INTEGER, date TIMESTAMP,
    battery_level SMALLINT, charger_power SMALLINT, charger_voltage INTEGER,
    charger_actual_current SMALLINT, charger_phases SMALLINT,
    rated_battery_range_km DOUBLE PRECISION, outside_temp DOUBLE PRECISION,
    fast_charger_present BOOLEAN, fast_charger_brand TEXT, fast_charger_type TEXT,
    conn_charge_cable TEXT, battery_heater_on BOOLEAN);
CREATE TABLE positions (id SERIAL PRIMARY KEY, car_id SMALLINT, date TIMESTAMP,
    latitude DOUBLE PRECISION, longitude DOUBLE PRECISION, battery_level SMALLINT,
    usable_battery_level SMALLINT, rated_battery_range_km DOUBLE PRECISION,
    ideal_battery_range_km DOUBLE PRECISION, est_battery_range_km DOUBLE PRECISION,
    odometer DOUBLE PRECISION, outside_temp DOUBLE PRECISION, is_climate_on BOOLEAN,
    inside_temp DOUBLE PRECISION, driver_temp_setting DOUBLE PRECISION, speed SMALLINT, power SMALLINT, drive_id INTEGER, elevation SMALLINT,
    tpms_pressure_fl DOUBLE PRECISION, tpms_pressure_fr DOUBLE PRECISION,
    tpms_pressure_rl DOUBLE PRECISION, tpms_pressure_rr DOUBLE PRECISION);
CREATE TABLE updates (id SERIAL PRIMARY KEY, car_id SMALLINT, version TEXT,
    start_date TIMESTAMP, end_date TIMESTAMP);
-- TeslaMate's state column is an enum (online, offline, asleep); the queries
-- compare it as text, so TEXT stands in for it here.
CREATE TABLE states (id SERIAL PRIMARY KEY, car_id SMALLINT, state TEXT,
    start_date TIMESTAMP, end_date TIMESTAMP);
-- TeslaMate's settings row; its unit columns are enums there, text here.
CREATE TABLE settings (id BIGSERIAL PRIMARY KEY, unit_of_length TEXT, unit_of_temperature TEXT,
    unit_of_pressure TEXT, preferred_range TEXT, language TEXT);
INSERT INTO settings (unit_of_length, unit_of_temperature, unit_of_pressure, preferred_range,
    language) VALUES ('mi', 'F', 'psi', 'ideal', 'en');

INSERT INTO car_settings (id) VALUES (1), (2);
INSERT INTO cars VALUES (1, 'Blue Thunder', 'model3', 'LR', 'DeepBlue', 'Model 3 LR', 1, 0.15),
                        (2, 'Red Rocket', 'modely', 'P', 'Red', 'Model Y P', 2, 0.16);
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
     42.0, 40, 110, 150, -30, 800.0, 842.0, 21.0, 8.0, 1, 2, 420.0, 400.0),
    (1, now() - interval '45 days', now() - interval '45 days' + interval '15 min',
     8.0, 15, 80, 100, -30, 1500.0, 1508.0, 21.0, 20.0, 2, 1, 350.0, 340.0),
    (1, now() - interval '45 days' + interval '12 hours',
     now() - interval '45 days' + interval '12 hours 14 min',
     7.0, 14, 70, 90, -25, 1508.0, 1515.0, 21.0, 20.0, 1, 2, 335.0, 328.0);
INSERT INTO geofences (id, name, latitude, longitude, radius, cost_per_unit, session_fee,
    billing_type) VALUES
    (1, 'Home', 41.0, 29.0, 25, 0.28, NULL, 'per_kwh');
INSERT INTO charging_processes (car_id, start_date, end_date, charge_energy_added,
    duration_min, cost, address_id, geofence_id, start_battery_level, end_battery_level,
    charge_energy_used) VALUES
    (1, now() - interval '1 day', now() - interval '1 day' + interval '30 min',
     30.0, 30, 12.50, 1, 1, 40, 80, 33.0),
    (1, now() - interval '10 days', now() - interval '10 days' + interval '40 min',
     50.0, 40, 30.00, 3, NULL, 20, 85, 54.0),
    (2, now() - interval '3 days', now() - interval '3 days' + interval '60 min',
     20.0, 60, NULL, 1, 1, 30, 55, 21.0);
INSERT INTO charges (charging_process_id, date, battery_level, charger_power, charger_voltage,
    charger_actual_current, charger_phases, rated_battery_range_km, outside_temp)
SELECT 1, now() - interval '1 day' + (n || ' minutes')::interval,
       50 + n, 11, 230, 16, 1, 300.0 + n, 15.0
FROM generate_series(0, 29) AS n;
-- DC fast-charge samples for session 2 (charger_phases NULL marks DC).
INSERT INTO charges (charging_process_id, date, battery_level, charger_power, charger_voltage,
    charger_actual_current, charger_phases, rated_battery_range_km, outside_temp)
SELECT 2, now() - interval '10 days' + (n * 8 || ' minutes')::interval,
       20 + 16 * n, 150, 400, 375, NULL, 100.0 + 60 * n, 18.0
FROM generate_series(0, 4) AS n;
INSERT INTO positions (car_id, date, latitude, longitude, battery_level, usable_battery_level,
    rated_battery_range_km, ideal_battery_range_km, est_battery_range_km, odometer, outside_temp,
    is_climate_on, tpms_pressure_fl, tpms_pressure_fr, tpms_pressure_rl, tpms_pressure_rr) VALUES
    (1, now() - interval '30 days', 41.0, 29.0, 100, 99, 420.0, 430.0, 415.0, 990.0, 12.0,
     FALSE, 2.9, 2.9, 2.8, 2.8),
    (1, now() - interval '1 hour', 41.05, 29.05, 80, 79, 330.0, 430.0, 320.0, 1012.5, 18.0,
     TRUE, 2.9, 3.0, 2.8, 2.9),
    (2, now() - interval '2 hours', 41.1, 29.1, 60, 59, 210.0, 350.0, 200.0, 505.0, 15.0,
     FALSE, 3.1, 3.1, 3.0, 3.0);
-- SOC-hygiene samples: recent, tpms NULL (tire query filters them out), battery < 100
-- (degradation query filters on = 100), and older than each car's latest position so
-- current_car_status still returns the rows seeded above.
INSERT INTO positions (car_id, date, battery_level, usable_battery_level) VALUES
    (1, now() - interval '3 days', 15, 14),
    (1, now() - interval '60 hours', 90, 89),
    (1, now() - interval '2 days', 55, 54),
    (2, now() - interval '3 days', 25, 24),
    (2, now() - interval '40 hours', 85, 84);
-- Route points inside the fixed TZ-boundary drive (id 4), for get_drive_route.
INSERT INTO positions (car_id, date, latitude, longitude, battery_level, usable_battery_level,
    odometer, speed, power, elevation)
SELECT 1, TIMESTAMP '2026-01-15 22:30:00' + (n * 3 || ' minutes')::interval,
       41.0 + 0.007 * n, 29.0 + 0.005 * n, 80 - n, 79 - n,
       800.0 + 3.8 * n, 40 + 5 * n, 20 + n, 100 + 10 * n
FROM generate_series(0, 11) AS n;
UPDATE drives SET ascent = 120, descent = 10 WHERE id = 4;
INSERT INTO updates (car_id, version, start_date, end_date) VALUES
    (1, '2026.20.1', now() - interval '5 days', now() - interval '5 days' + interval '25 min');
"""


# Opt-in extra seeds (mcp_session(seeds=[...]), or with_trips=True for "trips"),
# kept apart so the fleet-wide totals the other tests assert on stay unchanged.
_TRIP_SQL = """
-- Road trip for car 3 (fixed UTC dates), for the trip tools. With the default
-- limits (30 min plain stop, 120 min charging stop) drives 101-103 form one
-- trip: a 20-min WC stop, then a 70-min stop containing a 40-min charge. The
-- overnight stop (with a hotel charge) ends it; drive 105 follows drive 104
-- after a 45-min stop without charging, so it starts a trip of its own.
INSERT INTO car_settings (id) VALUES (3);
INSERT INTO cars VALUES (3, 'Road Tripper', 'modely', 'LR', 'White', 'Model Y LR', 3, 0.16);
INSERT INTO addresses VALUES
    (10, 'Bolu Rest Area', 'Bolu', 'TR-14', 40.73, 31.60),
    (11, 'Supercharger Bolu', 'Bolu', 'TR-14', 40.75, 31.62),
    (12, 'Kizilay Square', 'Ankara', 'TR-06', 39.92, 32.85),
    (13, 'Ankara Office', 'Ankara', 'TR-06', 39.95, 32.80);
INSERT INTO drives (id, car_id, start_date, end_date, distance, duration_min, speed_max,
    outside_temp_avg, start_address_id, end_address_id, start_rated_range_km,
    end_rated_range_km) VALUES
    (101, 3, TIMESTAMP '2025-06-10 06:00', TIMESTAMP '2025-06-10 07:30', 140.0, 90, 125,
     20.0, 1, 10, 450.0, 340.0),
    (102, 3, TIMESTAMP '2025-06-10 07:50', TIMESTAMP '2025-06-10 08:40', 70.0, 50, 120,
     22.0, 10, 11, 340.0, 285.0),
    (103, 3, TIMESTAMP '2025-06-10 09:50', TIMESTAMP '2025-06-10 11:20', 150.0, 90, 130,
     26.0, 11, 12, 420.0, 300.0),
    (104, 3, TIMESTAMP '2025-06-11 10:00', TIMESTAMP '2025-06-11 10:20', 15.0, 20, 70,
     24.0, 12, 13, 470.0, 458.0),
    (105, 3, TIMESTAMP '2025-06-11 11:05', TIMESTAMP '2025-06-11 11:25', 14.0, 20, 65,
     25.0, 13, 12, 458.0, 447.0);
INSERT INTO charging_processes (id, car_id, start_date, end_date, charge_energy_added,
    duration_min, address_id, start_battery_level, end_battery_level) VALUES
    (101, 3, TIMESTAMP '2025-06-10 08:45', TIMESTAMP '2025-06-10 09:25', 35.0, 40, 11, 30, 75),
    (102, 3, TIMESTAMP '2025-06-10 20:00', TIMESTAMP '2025-06-11 06:00', 40.0, 600, 12, 45, 95);
-- Four track points per trip drive: start, two in between, end.
INSERT INTO positions (car_id, date, latitude, longitude, battery_level, speed, elevation)
SELECT 3, d.start_date + (d.end_date - d.start_date) * (n / 3.0),
       sa.latitude + (ea.latitude - sa.latitude) * (n / 3.0),
       sa.longitude + (ea.longitude - sa.longitude) * (n / 3.0),
       (d.start_rated_range_km - (d.start_rated_range_km - d.end_rated_range_km) * (n / 3.0))
           / 5.0,
       60 + 10 * n,
       100 + 250 * (d.id - 101) + 60 * n
FROM drives d
    JOIN addresses sa ON sa.id = d.start_address_id
    JOIN addresses ea ON ea.id = d.end_address_id
    CROSS JOIN generate_series(0, 3) AS n
WHERE d.car_id = 3;
UPDATE drives d
SET start_position_id = (SELECT p.id FROM positions p WHERE p.car_id = 3 AND p.date = d.start_date),
    end_position_id = (SELECT p.id FROM positions p WHERE p.car_id = 3 AND p.date = d.end_date),
    ascent = 100,
    descent = 50
WHERE d.car_id = 3;
"""

# Cars 4-7 for the state tools. Car 4's states are laid out from UTC midnight
# two days ago (D) so day buckets are deterministic under the default UTC
# REPORT_TIMEZONE:
#   day D:   online 00:00-02:30, asleep from 02:30
#   day D+1: asleep until 06:00, online 06:00-09:00 (a 30-min drive and a
#            30-min charge inside it), offline 09:00-24:00
#   today:   asleep since midnight (open state)
# Car 4 also has an orphaned open drive (no end_date), which must not count as
# driving time. Car 5 is driving now and car 6 is charging now. Car 7's online
# state has been open since D, but TeslaMate last logged a position at D 01:00,
# during an orphaned open drive: it must read as online, not driving.
_STATE_SQL = """
INSERT INTO car_settings (id) VALUES (4), (5), (6), (7);
INSERT INTO cars VALUES (4, 'Night Owl', 'model3', 'SR', 'White', 'Model 3 SR', 4),
                        (5, 'Road Runner', 'model3', 'LR', 'Grey', 'Model 3 LR', 5),
                        (6, 'Plug Star', 'modely', 'LR', 'Black', 'Model Y LR', 6),
                        (7, 'Ghost Car', 'models', 'P', 'Silver', 'Model S P', 7);
CREATE TEMP TABLE base AS
    SELECT date_trunc('day', now() AT TIME ZONE 'UTC') - interval '2 days' AS d,
        now() AT TIME ZONE 'UTC' AS utc_now;
INSERT INTO states (car_id, state, start_date, end_date)
SELECT v.car_id, v.state, base.d + v.start_off, base.d + v.end_off
FROM base
    CROSS JOIN (VALUES
        (4, 'online', interval '0 hours', interval '2.5 hours'),
        (4, 'asleep', interval '2.5 hours', interval '30 hours'),
        (4, 'online', interval '30 hours', interval '33 hours'),
        (4, 'offline', interval '33 hours', interval '48 hours'),
        (4, 'asleep', interval '48 hours', NULL::interval),
        (7, 'online', interval '0 hours', NULL::interval)
    ) AS v(car_id, state, start_off, end_off);
INSERT INTO states (car_id, state, start_date, end_date)
SELECT 5, 'online', utc_now - interval '20 minutes', NULL::timestamp FROM base
UNION ALL SELECT 6, 'online', utc_now - interval '2 hours', NULL FROM base;
INSERT INTO drives (id, car_id, start_date, end_date, distance, duration_min, start_address_id,
    end_address_id, start_rated_range_km, end_rated_range_km)
SELECT 201, 4, d + interval '31 hours', d + interval '31.5 hours', 20.0, 30, 1, 2, 300.0, 290.0
FROM base
UNION ALL SELECT 202, 4, d + interval '1 hour', NULL, NULL, NULL, 1, NULL, 310.0, NULL FROM base
UNION ALL SELECT 203, 5, utc_now - interval '10 minutes', NULL, NULL, NULL, 2, NULL, 400.0, NULL
FROM base
UNION ALL SELECT 204, 7, d + interval '0.5 hours', NULL, NULL, NULL, 1, NULL, 350.0, NULL FROM base;
INSERT INTO charging_processes (id, car_id, start_date, end_date, charge_energy_added,
    duration_min, address_id, start_battery_level, end_battery_level)
SELECT 201, 4, d + interval '32 hours', d + interval '32.5 hours', 5.0, 30, 2, 60, 66 FROM base
UNION ALL SELECT 202, 6, utc_now - interval '1 hour', NULL, NULL, NULL, 1, 40, NULL FROM base;
INSERT INTO charges (charging_process_id, date, battery_level, charger_power, charger_phases)
SELECT 202, utc_now - interval '5 minutes', 55, 11, 3 FROM base;
INSERT INTO positions (car_id, date, latitude, longitude, battery_level, drive_id)
SELECT 4, d + interval '33 hours', 41.1, 29.1, 66, NULL FROM base
UNION ALL SELECT 5, utc_now - interval '1 minute', 41.05, 29.05, 78, 203 FROM base
UNION ALL SELECT 6, utc_now - interval '5 minutes', 41.0, 29.0, 55, NULL FROM base
UNION ALL SELECT 7, d + interval '1 hour', 41.0, 29.0, 70, 204 FROM base;
-- Open online states end at the car's last position with an ideal range.
UPDATE positions SET ideal_battery_range_km = 300.0 WHERE car_id IN (4, 5, 6, 7);
DROP TABLE base;
"""

# Car 8 for get_trip_energy_estimate and get_efficiency_by_elevation,
# efficiency 0.15 kWh per rated km:
#   5 city drives at 20°C: 10 km, 10 rated km used -> 150 Wh/km, 50 m net descent
#   5 city drives at 0°C: 10 km, 14 rated km used -> 210 Wh/km, 150 m net climb
#   5 motorway drives at 20°C: 100 km in 60 min, 120 rated km used -> 180 Wh/km, flat
# and charges adding 4 rated km per battery percent (0.6 kWh, 60 kWh full).
_ESTIMATE_SQL = """
INSERT INTO car_settings (id) VALUES (8);
INSERT INTO cars VALUES (8, 'Planner', 'model3', 'LR', 'Blue', 'Model 3 LR', 8, 0.15);
INSERT INTO drives (car_id, start_date, end_date, distance, duration_min, outside_temp_avg,
    start_rated_range_km, end_rated_range_km, ascent, descent)
SELECT 8, now() - make_interval(days => n), now() - make_interval(days => n)
        + make_interval(mins => v.minutes),
    v.km, v.minutes, v.temp, 400.0, 400.0 - v.rated_used, v.ascent, v.descent
FROM generate_series(1, 5) AS n
    CROSS JOIN (VALUES (10.0, 20, 20.0, 10.0, 20, 70), (10.0, 20, 0.0, 14.0, 160, 10),
                       (100.0, 60, 20.0, 120.0, 1000, 1000))
        AS v(km, minutes, temp, rated_used, ascent, descent);
INSERT INTO charging_processes (car_id, start_date, end_date, charge_energy_added,
    start_battery_level, end_battery_level, start_rated_range_km, end_rated_range_km)
SELECT 8, now() - make_interval(days => n, hours => 12),
    now() - make_interval(days => n, hours => 11), 36.0, 20, 80, 80.0, 320.0
FROM generate_series(1, 3) AS n;
INSERT INTO positions (car_id, date, battery_level, ideal_battery_range_km)
VALUES (8, now() - interval '10 minutes', 80, 330.0);
"""

# Cars 9 ("Penny") and 10 ("Freebie", free Supercharging) for the cost tools.
# Penny paid 0.50 and 0.60 per billed kWh at the Bursa Supercharger (billed =
# the larger of kWh used and kWh added); its sessions 303-305 have no cost.
# The base seed adds one costed AC session (0.3788/kWh) and one costed
# third-party DC session (0.5556/kWh) that serve as charger-type history.
_COST_SQL = """
INSERT INTO car_settings (id, free_supercharging) VALUES (9, FALSE), (10, TRUE);
INSERT INTO cars VALUES (9, 'Penny', 'model3', 'SR', 'Red', 'Model 3 SR', 9, 0.14),
                        (10, 'Freebie', 'models', 'LR', 'Black', 'Model S LR', 10, 0.18);
INSERT INTO addresses VALUES
    (20, 'Tesla Supercharger Bursa', 'Bursa', 'TR-16', 40.2, 29.0),
    (21, 'Mall DC Charger', 'Bursa', 'TR-16', 40.21, 29.05),
    (22, 'Garage Plug', 'Bursa', 'TR-16', 40.22, 29.1);
INSERT INTO charging_processes (id, car_id, start_date, end_date, charge_energy_added,
    charge_energy_used, duration_min, cost, address_id) VALUES
    (301, 9, now() - interval '30 days', now() - interval '30 days' + interval '30 min',
     38.0, 40.0, 30, 20.00, 20),
    (302, 9, now() - interval '20 days', now() - interval '20 days' + interval '30 min',
     38.0, 40.0, 30, 24.00, 20),
    (303, 9, now() - interval '10 days', now() - interval '10 days' + interval '25 min',
     28.0, 30.0, 25, NULL, 20),
    (304, 9, now() - interval '8 days', now() - interval '8 days' + interval '20 min',
     19.0, 20.0, 20, NULL, 21),
    (305, 9, now() - interval '6 days', now() - interval '6 days' + interval '60 min',
     10.0, 11.0, 60, NULL, 22),
    (306, 10, now() - interval '5 days', now() - interval '5 days' + interval '30 min',
     30.0, 31.0, 30, NULL, 20),
    (307, 9, now() - interval '4 days', now() - interval '4 days' + interval '1 min',
     0.0, 0.0, 1, NULL, 22);
INSERT INTO charges (charging_process_id, date, battery_level, charger_power, charger_phases,
    fast_charger_present, fast_charger_brand, fast_charger_type)
SELECT cp.id, cp.start_date + interval '1 min', 50, v.power, v.phases, v.present, v.brand,
    v.kind
FROM charging_processes cp
    JOIN (VALUES
        (20, 120, NULL::int, TRUE, 'Tesla', 'Combo'),
        (21, 90, NULL::int, TRUE, '<invalid>', 'Combo'),
        (22, 11, 3, FALSE, NULL, 'ACSingleWireCAN')
    ) AS v(address_id, power, phases, present, brand, kind) ON v.address_id = cp.address_id
WHERE cp.id BETWEEN 301 AND 307;
"""

# Car 11 ("Sparky") for the fast-charging tools:
#   401 Supercharger, 10% -> 85% in 76 one-minute samples: 150 kW up to 50%,
#       then 3 kW less per percent (45 kW at 85%)
#   402 third-party DC, 30% -> 60% at a flat 60 kW, battery heater on at first
#   403 AC at 11 kW that ends on a 0 kW sample with no phases, the sample that
#       used to make AC sessions count as DC
_FAST_SQL = """
INSERT INTO car_settings (id) VALUES (11);
INSERT INTO cars VALUES (11, 'Sparky', 'model3', 'LR', 'Blue', 'Model 3 LR', 11, 0.15);
INSERT INTO addresses VALUES
    (30, 'Tesla Supercharger Gebze', 'Gebze', 'TR-41', 40.8, 29.4),
    (31, 'Outlet DC Charger', 'Izmit', 'TR-41', 40.76, 29.9),
    (32, 'Sparky Garage', 'Izmit', 'TR-41', 40.77, 29.95);
INSERT INTO charging_processes (id, car_id, start_date, end_date, charge_energy_added,
    charge_energy_used, duration_min, cost, address_id, start_battery_level,
    end_battery_level) VALUES
    (401, 11, date_trunc('minute', now()) - interval '5 days',
     date_trunc('minute', now()) - interval '5 days' + interval '76 min',
     76.0, 80.0, 76, 38.00, 30, 10, 85),
    (402, 11, date_trunc('minute', now()) - interval '2 days',
     date_trunc('minute', now()) - interval '2 days' + interval '31 min',
     25.0, 27.0, 31, NULL, 31, 30, 60),
    (403, 11, date_trunc('minute', now()) - interval '1 day',
     date_trunc('minute', now()) - interval '1 day' + interval '22 min',
     10.0, 12.0, 22, NULL, 32, 40, 60);
INSERT INTO charges (charging_process_id, date, battery_level, charger_power, charger_phases,
    fast_charger_present, fast_charger_brand, fast_charger_type, battery_heater_on)
SELECT 401, cp.start_date + make_interval(mins => n), 10 + n,
    CASE WHEN 10 + n <= 50 THEN 150 ELSE 150 - (10 + n - 50) * 3 END,
    NULL::int, TRUE, 'Tesla', 'Combo', FALSE
FROM charging_processes cp CROSS JOIN generate_series(0, 75) AS n WHERE cp.id = 401
UNION ALL
SELECT 402, cp.start_date + make_interval(mins => n), 30 + n, 60, NULL, TRUE, '<invalid>',
    'Combo', n < 10
FROM charging_processes cp CROSS JOIN generate_series(0, 30) AS n WHERE cp.id = 402
UNION ALL
SELECT 403, cp.start_date + make_interval(mins => n), 40 + n, 11, 3, FALSE, NULL,
    'ACSingleWireCAN', FALSE
FROM charging_processes cp CROSS JOIN generate_series(0, 20) AS n WHERE cp.id = 403
UNION ALL
SELECT 403, cp.start_date + interval '22 min', 60, 0, NULL, FALSE, NULL, 'ACSingleWireCAN',
    FALSE
FROM charging_processes cp WHERE cp.id = 403;
"""

# Car 12 ("Chiller") for the parked-climate tools. Day D is three UTC days back.
# Drives 501 (08:00-08:30), 502 (18:00-18:30) and 503 (D+1 09:00) bound two
# parks. Polled samples (climate state set) make four climate sessions:
#   08:31-08:37  after_drive, cooling (30 °C out, 22 set), 2 kW: 6 min, 0.2 kWh
#   12:00-12:20  parked (Dog mode), cooling, 3 kW; the last sample's credit is
#                capped at 10 min: 20 min, 1.0 kWh
#   17:50-18:00  before_drive, heating (5 °C out, 21 set), 4 kW; cut at the
#                drive's start: 10 min, 0.67 kWh
#   18:45-19:00  plugged in (charge 18:40-20:00, 0.50 per kWh): 15 min, 0 kWh
_CLIMATE_SQL = """
INSERT INTO car_settings (id) VALUES (12);
INSERT INTO cars VALUES (12, 'Chiller', 'model3', 'LR', 'White', 'Model 3 LR', 12, 0.15);
INSERT INTO addresses VALUES (40, 'Chiller Home', 'Izmir', 'TR-35', 38.4, 27.1),
                             (41, 'Chiller Office', 'Izmir', 'TR-35', 38.45, 27.2);
CREATE TEMP TABLE base AS
    SELECT date_trunc('day', now() AT TIME ZONE 'UTC') - interval '3 days' AS d;
INSERT INTO drives (id, car_id, start_date, end_date, distance, duration_min, start_address_id,
    end_address_id, start_rated_range_km, end_rated_range_km)
SELECT 501, 12, d + interval '8 hours', d + interval '8.5 hours', 20.0, 30, 40, 41, 400.0, 380.0
FROM base
UNION ALL SELECT 502, 12, d + interval '18 hours', d + interval '18.5 hours', 20.0, 30, 41, 40,
    375.0, 355.0 FROM base
UNION ALL SELECT 503, 12, d + interval '33 hours', d + interval '33.3 hours', 10.0, 20, 40, 41,
    350.0, 340.0 FROM base;
INSERT INTO charging_processes (id, car_id, start_date, end_date, charge_energy_added,
    charge_energy_used, duration_min, cost, address_id)
SELECT 501, 12, d + interval '18 hours 40 minutes', d + interval '20 hours', 20.0, 20.0, 80,
    10.00, 40 FROM base;
INSERT INTO positions (car_id, date, latitude, longitude, is_climate_on, power, outside_temp,
    inside_temp, driver_temp_setting)
SELECT 12, d + v.at, 38.4, 27.1, v.on_, v.kw, v.outside, 25.0, v.setpoint
FROM base
    CROSS JOIN (VALUES
        (interval '8 hours 31 minutes', TRUE, 2, 30.0, 22.0),
        (interval '8 hours 34 minutes', TRUE, 2, 30.0, 22.0),
        (interval '8 hours 37 minutes', FALSE, 0, 30.0, 22.0),
        (interval '12 hours', TRUE, 3, 30.0, 22.0),
        (interval '12 hours 5 minutes', TRUE, 3, 30.0, 22.0),
        (interval '12 hours 10 minutes', TRUE, 3, 30.0, 22.0),
        (interval '12 hours 20 minutes', FALSE, 0, 30.0, 22.0),
        (interval '17 hours 50 minutes', TRUE, 4, 5.0, 21.0),
        (interval '17 hours 55 minutes', TRUE, 4, 5.0, 21.0),
        (interval '18 hours 45 minutes', TRUE, -10, 20.0, 22.0),
        (interval '18 hours 50 minutes', TRUE, -10, 20.0, 22.0)
    ) AS v(at, on_, kw, outside, setpoint);
DROP TABLE base;
"""

_EXTRA_SEEDS = {
    "trips": _TRIP_SQL,
    "states": _STATE_SQL,
    "estimate": _ESTIMATE_SQL,
    "costs": _COST_SQL,
    "fast": _FAST_SQL,
    "climate": _CLIMATE_SQL,
}


@pytest.fixture(scope="session")
def postgres_container():
    """Start a single Postgres container for the test session.

    Returns the container instance (None when TESLAMATE_TEST_DATABASE_URL
    points at an existing server), or skips all integration tests when Docker
    is unavailable. Sharing one container across the session keeps test
    startup time bounded.
    """
    if os.environ.get("TESLAMATE_TEST_DATABASE_URL"):
        yield None
        return
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
    if postgres_container is None:
        return os.environ["TESLAMATE_TEST_DATABASE_URL"]
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
    """Factory: an initialized in-memory MCP client against a real server.

    Runs the full MCPServer stack (lifespan, pool, tool dispatch) without HTTP.
    Accepts Settings overrides, e.g. mcp_session(report_timezone="Europe/Istanbul"),
    and seeds=[...] naming extra seeds from _EXTRA_SEEDS (with_trips=True is
    shorthand for seeds=["trips"], the car-3 road trip).
    """

    @asynccontextmanager
    async def factory(*, elicitation_callback=None, with_trips=False, seeds=(), **overrides):
        extra = [*seeds, *(["trips"] if with_trips else [])]
        if extra:
            async with await psycopg.AsyncConnection.connect(
                seeded_database, autocommit=True
            ) as conn:
                for name in extra:
                    await conn.execute(_EXTRA_SEEDS[name])
        settings = Settings(database_url=seeded_database, **overrides)  # type: ignore[call-arg]
        mcp = create_server(settings)
        try:
            # The in-memory client advertises the elicitation capability only
            # when a callback is passed, so both confirm branches are reachable.
            async with Client(
                mcp, raise_exceptions=False, elicitation_callback=elicitation_callback
            ) as client:
                yield client
        finally:
            # The lifespan closes the pool on client exit; this covers the
            # case where connection setup failed partway through.
            await mcp.teslamate_app_context.pool.close()  # type: ignore[attr-defined]

    return factory
