-- Rated range at 100 %% against the odometer, like TeslaMate's Projected Range
-- dashboard but read from charge ends: a charge that stopped at 50 %% or more
-- gives a steady reading, while a low level scaled up to 100 %% magnifies its
-- rounding. Each charge takes the odometer of the car's last drive before it.
WITH readings AS (
    SELECT cp.car_id,
        cp.end_date,
        cp.end_rated_range_km * 100 / cp.end_battery_level AS range_at_100,
        odo.km
    FROM charging_processes cp
        JOIN cars c ON c.id = cp.car_id
        CROSS JOIN LATERAL (
            SELECT d.end_km AS km
            FROM drives d
            WHERE d.car_id = cp.car_id
                AND d.end_date <= cp.start_date
                AND d.end_km IS NOT NULL
            ORDER BY d.end_date DESC
            LIMIT 1
        ) odo
    WHERE cp.end_date IS NOT NULL
        AND cp.end_battery_level >= 50
        AND cp.end_rated_range_km > 0
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
buckets AS (
    SELECT car_id,
        FLOOR(km / %(bucket_km)s::int)::int * %(bucket_km)s::int AS odometer_from,
        COUNT(*) AS charges,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY range_at_100) AS range_at_100,
        MIN(range_at_100) AS min_range,
        MAX(range_at_100) AS max_range,
        MIN(end_date) AS first_at,
        MAX(end_date) AS last_at
    FROM readings
    GROUP BY car_id, 2
)
SELECT c.name AS car_name,
    b.odometer_from AS odometer_from_km,
    b.odometer_from + %(bucket_km)s::int AS odometer_to_km,
    b.charges,
    ROUND(b.range_at_100::numeric, 1) AS range_at_100_km,
    ROUND(b.min_range::numeric, 1) AS min_range_at_100_km,
    ROUND(b.max_range::numeric, 1) AS max_range_at_100_km,
    -- Against the car's best bucket: the newest car is not always the first
    -- bucket, since range estimates settle over the first months.
    ROUND((100 * (b.range_at_100 / MAX(b.range_at_100) OVER (PARTITION BY b.car_id) - 1))::numeric, 1)
        AS vs_best_pct,
    TO_CHAR(((b.first_at AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date, 'YYYY-MM-DD')
        AS first_date,
    TO_CHAR(((b.last_at AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date, 'YYYY-MM-DD')
        AS last_date
FROM buckets b
    JOIN cars c ON c.id = b.car_id
ORDER BY c.name, b.odometer_from;
