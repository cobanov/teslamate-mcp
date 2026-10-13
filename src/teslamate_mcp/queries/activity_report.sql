-- A month by day, or a year by month: driving, energy, and charging per
-- bucket, with empty buckets kept so the report shows gaps. Buckets are
-- local calendar days or months (REPORT_TIMEZONE).
WITH today AS (
    SELECT (now() AT TIME ZONE %(tz)s::text)::date AS d
),
bounds AS (
    SELECT first_day,
        (first_day + CASE WHEN %(period)s::text = 'year' THEN interval '1 year'
            ELSE interval '1 month' END)::date AS end_day,
        CASE WHEN %(period)s::text = 'year' THEN interval '1 month' ELSE interval '1 day' END
            AS step
    FROM (
        SELECT CASE WHEN %(period)s::text = 'year'
                THEN make_date(COALESCE(%(year)s::int, EXTRACT(YEAR FROM t.d)::int), 1, 1)
                ELSE make_date(
                    COALESCE(%(year)s::int, EXTRACT(YEAR FROM t.d)::int),
                    COALESCE(%(month)s::int, EXTRACT(MONTH FROM t.d)::int),
                    1
                )
            END AS first_day
        FROM today t
    ) f
),
buckets AS (
    SELECT b::date AS bucket
    FROM bounds,
        generate_series(first_day::timestamp, (end_day - step)::timestamp, step) AS b
),
scope_cars AS (
    SELECT c.id,
        c.efficiency
    FROM cars c
    WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
drive_days AS (
    SELECT ((d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date AS day,
        d.distance,
        d.duration_min,
        d.outside_temp_avg,
        (d.start_rated_range_km - d.end_rated_range_km) * c.efficiency AS kwh
    FROM drives d
        JOIN scope_cars c ON c.id = d.car_id
    WHERE d.end_date IS NOT NULL
),
drive_agg AS (
    SELECT CASE WHEN %(period)s::text = 'year' THEN date_trunc('month', dd.day)::date
            ELSE dd.day END AS bucket,
        COUNT(*) AS drives,
        SUM(dd.distance) AS km,
        SUM(dd.duration_min) AS minutes,
        SUM(dd.kwh) AS kwh,
        SUM(dd.outside_temp_avg * dd.duration_min) FILTER (WHERE dd.outside_temp_avg IS NOT NULL)
            / NULLIF(SUM(dd.duration_min) FILTER (WHERE dd.outside_temp_avg IS NOT NULL), 0)
            AS temp
    FROM drive_days dd
        CROSS JOIN bounds
    WHERE dd.day >= bounds.first_day
        AND dd.day < bounds.end_day
    GROUP BY 1
),
charge_agg AS (
    SELECT CASE WHEN %(period)s::text = 'year' THEN date_trunc('month', cd.day)::date
            ELSE cd.day END AS bucket,
        COUNT(*) AS sessions,
        SUM(cd.charge_energy_added) AS kwh_added,
        SUM(cd.cost) AS cost
    FROM (
        SELECT ((cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date AS day,
            cp.charge_energy_added,
            cp.cost
        FROM charging_processes cp
        WHERE cp.end_date IS NOT NULL
            AND cp.car_id IN (SELECT id FROM scope_cars)
    ) cd
        CROSS JOIN bounds
    WHERE cd.day >= bounds.first_day
        AND cd.day < bounds.end_day
    GROUP BY 1
)
SELECT TO_CHAR(b.bucket, CASE WHEN %(period)s::text = 'year' THEN 'YYYY-MM' ELSE 'YYYY-MM-DD' END)
        AS bucket,
    COALESCE(da.drives, 0) AS drives,
    ROUND(COALESCE(da.km, 0)::numeric, 1) AS distance_km,
    ROUND((COALESCE(da.minutes, 0) / 60.0)::numeric, 1) AS driving_hours,
    ROUND(COALESCE(da.kwh, 0)::numeric, 1) AS energy_used_kwh,
    ROUND((da.kwh * 1000 / NULLIF(da.km, 0))::numeric) AS wh_per_km,
    COALESCE(ca.sessions, 0) AS charging_sessions,
    ROUND(COALESCE(ca.kwh_added, 0)::numeric, 1) AS kwh_added,
    ROUND(ca.cost::numeric, 2) AS charging_cost,
    ROUND(da.temp::numeric, 1) AS avg_outside_temp
FROM buckets b
    LEFT JOIN drive_agg da ON da.bucket = b.bucket
    LEFT JOIN charge_agg ca ON ca.bucket = b.bucket
ORDER BY b.bucket;
