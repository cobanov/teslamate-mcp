-- A year or a month in one row: totals, the change against the period before,
-- and highlights (longest drive, busiest day, favourite places, extremes).
-- Periods are local calendar years or months (REPORT_TIMEZONE); their bounds
-- are converted to UTC once so the drive and charge filters stay sargable.
WITH today AS (
    SELECT (now() AT TIME ZONE %(tz)s::text)::date AS d
),
bounds AS (
    SELECT f.first_day,
        (f.first_day + f.step)::date AS end_day,
        (f.first_day - f.step)::date AS prev_day,
        f.step,
        (f.first_day::timestamp AT TIME ZONE %(tz)s::text) AT TIME ZONE 'UTC' AS start_utc,
        ((f.first_day + f.step)::timestamp AT TIME ZONE %(tz)s::text) AT TIME ZONE 'UTC'
            AS end_utc,
        ((f.first_day - f.step)::timestamp AT TIME ZONE %(tz)s::text) AT TIME ZONE 'UTC'
            AS prev_utc
    FROM (
        SELECT CASE WHEN %(period)s::text = 'year'
                THEN make_date(COALESCE(%(year)s::int, EXTRACT(YEAR FROM t.d)::int), 1, 1)
                ELSE make_date(
                    COALESCE(%(year)s::int, EXTRACT(YEAR FROM t.d)::int),
                    COALESCE(%(month)s::int, EXTRACT(MONTH FROM t.d)::int),
                    1
                )
            END AS first_day,
            CASE WHEN %(period)s::text = 'year' THEN interval '1 year'
                ELSE interval '1 month' END AS step
        FROM today t
    ) f
),
scope_cars AS (
    SELECT c.id,
        c.efficiency
    FROM cars c
    WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
period_drives AS (
    SELECT d.*,
        ((d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date AS local_day,
        (d.start_rated_range_km - d.end_rated_range_km) * c.efficiency AS kwh
    FROM drives d
        JOIN scope_cars c ON c.id = d.car_id
        CROSS JOIN bounds b
    WHERE d.end_date IS NOT NULL
        AND d.start_date >= b.start_utc
        AND d.start_date < b.end_utc
),
period_charges AS (
    SELECT cp.*,
        EXISTS (
            SELECT 1
            FROM charges ch
            WHERE ch.charging_process_id = cp.id
                AND (ch.fast_charger_present OR (ch.charger_phases IS NULL AND ch.charger_power > 0))
        ) AS is_dc
    FROM charging_processes cp
        CROSS JOIN bounds b
    WHERE cp.car_id IN (SELECT id FROM scope_cars)
        AND cp.end_date IS NOT NULL
        AND cp.start_date >= b.start_utc
        AND cp.start_date < b.end_utc
),
totals AS (
    SELECT COUNT(*) AS drives,
        SUM(pd.distance) AS km,
        SUM(pd.duration_min) AS minutes,
        COUNT(DISTINCT pd.local_day) AS days_driven,
        SUM(pd.kwh) AS kwh,
        MAX(pd.speed_max) AS top_speed,
        MIN(pd.outside_temp_avg) AS coldest,
        MAX(pd.outside_temp_avg) AS hottest,
        MAX(pd.end_km) AS odometer
    FROM period_drives pd
),
-- The period before, cut at the same point when this one is still running,
-- so a year in progress is not measured against a whole year.
previous AS (
    SELECT SUM(d.distance) AS km
    FROM drives d
        CROSS JOIN bounds b
    WHERE d.car_id IN (SELECT id FROM scope_cars)
        AND d.end_date IS NOT NULL
        AND d.start_date >= b.prev_utc
        AND d.start_date < LEAST(b.start_utc,
            b.prev_utc + (LEAST(now() AT TIME ZONE 'UTC', b.end_utc) - b.start_utc))
),
charging AS (
    SELECT COUNT(*) AS sessions,
        COUNT(*) FILTER (WHERE pc.is_dc) AS dc_sessions,
        SUM(pc.charge_energy_added) AS kwh_added,
        SUM(pc.cost) AS cost
    FROM period_charges pc
),
longest AS (
    SELECT pd.distance,
        pd.local_day,
        COALESCE(sg.name, sa.display_name) AS from_place,
        COALESCE(eg.name, ea.display_name) AS to_place
    FROM period_drives pd
        LEFT JOIN addresses sa ON sa.id = pd.start_address_id
        LEFT JOIN addresses ea ON ea.id = pd.end_address_id
        LEFT JOIN geofences sg ON sg.id = pd.start_geofence_id
        LEFT JOIN geofences eg ON eg.id = pd.end_geofence_id
    ORDER BY pd.distance DESC NULLS LAST, pd.start_date
    LIMIT 1
),
busiest AS (
    SELECT pd.local_day,
        SUM(pd.distance) AS km
    FROM period_drives pd
    GROUP BY pd.local_day
    ORDER BY km DESC NULLS LAST, pd.local_day
    LIMIT 1
),
-- The most efficient day (month period) or month (year period), among those
-- with enough driving for the figure to mean something.
efficient AS (
    SELECT CASE WHEN %(period)s::text = 'year' THEN TO_CHAR(pd.local_day, 'YYYY-MM')
            ELSE TO_CHAR(pd.local_day, 'YYYY-MM-DD') END AS bucket,
        SUM(pd.kwh) * 1000 / NULLIF(SUM(pd.distance), 0) AS wh_per_km
    FROM period_drives pd
    GROUP BY 1
    HAVING SUM(pd.distance) >= CASE WHEN %(period)s::text = 'year' THEN 100 ELSE 20 END
        AND SUM(pd.kwh) > 0
    ORDER BY wh_per_km, bucket
    LIMIT 1
),
destination AS (
    SELECT COALESCE(g.name, a.display_name) AS place,
        COUNT(*) AS arrivals
    FROM period_drives pd
        LEFT JOIN addresses a ON a.id = pd.end_address_id
        LEFT JOIN geofences g ON g.id = pd.end_geofence_id
    WHERE COALESCE(g.name, a.display_name) IS NOT NULL
    GROUP BY 1
    ORDER BY arrivals DESC, place
    LIMIT 1
),
charge_place AS (
    SELECT COALESCE(g.name, a.display_name) AS place,
        COUNT(*) AS sessions
    FROM period_charges pc
        LEFT JOIN addresses a ON a.id = pc.address_id
        LEFT JOIN geofences g ON g.id = pc.geofence_id
    WHERE COALESCE(g.name, a.display_name) IS NOT NULL
    GROUP BY 1
    ORDER BY sessions DESC, place
    LIMIT 1
),
software AS (
    SELECT COUNT(*) AS updates,
        (ARRAY_AGG(u.version ORDER BY u.start_date DESC))[1] AS latest
    FROM updates u
        CROSS JOIN bounds b
    WHERE u.car_id IN (SELECT id FROM scope_cars)
        AND u.start_date >= b.start_utc
        AND u.start_date < b.end_utc
)
SELECT CASE WHEN %(period)s::text = 'year' THEN TO_CHAR(b.first_day, 'YYYY')
        ELSE TO_CHAR(b.first_day, 'YYYY-MM') END AS period,
    TO_CHAR(b.first_day, 'YYYY-MM-DD') AS period_start,
    TO_CHAR(b.end_day - 1, 'YYYY-MM-DD') AS period_end,
    (SELECT d FROM today) < b.end_day AS in_progress,
    COALESCE(t.drives, 0) AS drives,
    ROUND(COALESCE(t.km, 0)::numeric, 1) AS distance_km,
    ROUND((COALESCE(t.minutes, 0) / 60.0)::numeric, 1) AS driving_hours,
    COALESCE(t.days_driven, 0) AS days_driven,
    ROUND(COALESCE(t.kwh, 0)::numeric, 1) AS energy_used_kwh,
    ROUND((t.kwh * 1000 / NULLIF(t.km, 0))::numeric) AS wh_per_km,
    ROUND(p.km::numeric, 1) AS previous_distance_km,
    ROUND(((COALESCE(t.km, 0) - p.km) * 100 / NULLIF(p.km, 0))::numeric, 1)
        AS distance_change_pct,
    ROUND(t.odometer::numeric) AS odometer_km,
    COALESCE(ch.sessions, 0) AS charging_sessions,
    COALESCE(ch.dc_sessions, 0) AS dc_sessions,
    ROUND(COALESCE(ch.kwh_added, 0)::numeric, 1) AS kwh_added,
    ROUND(ch.cost::numeric, 2) AS charging_cost,
    ROUND(l.distance::numeric, 1) AS longest_drive_km,
    TO_CHAR(l.local_day, 'YYYY-MM-DD') AS longest_drive_date,
    l.from_place AS longest_drive_from,
    l.to_place AS longest_drive_to,
    TO_CHAR(bu.local_day, 'YYYY-MM-DD') AS busiest_day,
    ROUND(bu.km::numeric, 1) AS busiest_day_km,
    e.bucket AS most_efficient,
    ROUND(e.wh_per_km::numeric) AS most_efficient_wh_per_km,
    de.place AS top_destination,
    de.arrivals AS top_destination_arrivals,
    cpl.place AS top_charging_location,
    cpl.sessions AS top_charging_location_sessions,
    t.top_speed AS top_speed_kmh,
    ROUND(t.coldest::numeric, 1) AS coldest_drive_temp,
    ROUND(t.hottest::numeric, 1) AS hottest_drive_temp,
    COALESCE(sw.updates, 0) AS software_updates,
    sw.latest AS latest_version
FROM bounds b
    CROSS JOIN totals t
    CROSS JOIN previous p
    CROSS JOIN charging ch
    CROSS JOIN software sw
    LEFT JOIN longest l ON TRUE
    LEFT JOIN busiest bu ON TRUE
    LEFT JOIN efficient e ON TRUE
    LEFT JOIN destination de ON TRUE
    LEFT JOIN charge_place cpl ON TRUE;
