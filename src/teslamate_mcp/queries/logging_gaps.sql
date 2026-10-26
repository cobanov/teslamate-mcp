-- Logger holes: drives or charges TeslaMate never closed, and stretches with
-- no position samples that hide a drive or a charge. A parked car logs
-- nothing, so a hole counts only when the odometer moved or the battery level
-- rose across it. A drop alone is idle drain, so it does not count. A night
-- asleep is a normal hole, so min_hours defaults to 24. The position scan
-- covers the last `days` plus the one sample before that window, so a hole
-- that crosses the window edge still shows.
WITH bounds AS (
    SELECT (now() AT TIME ZONE 'UTC') - make_interval(days => %(days)s::int) AS start_at
),
scope AS (
    SELECT c.id,
        c.name
    FROM cars c
    WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
samples AS (
    SELECT p.car_id,
        p.date,
        p.odometer,
        p.battery_level
    FROM positions p
        CROSS JOIN bounds b
    WHERE p.car_id IN (SELECT id FROM scope)
        AND p.date >= b.start_at
    UNION ALL
    SELECT c.id AS car_id,
        p.date,
        p.odometer,
        p.battery_level
    FROM scope c
        CROSS JOIN bounds b
        JOIN LATERAL (
            SELECT pos.date,
                pos.odometer,
                pos.battery_level
            FROM positions pos
            WHERE pos.car_id = c.id
                AND pos.date < b.start_at
            ORDER BY pos.date DESC
            LIMIT 1
        ) p ON true
),
holes AS (
    SELECT s.car_id,
        LAG(s.date) OVER w AS started_at,
        s.date AS ended_at,
        s.odometer - LAG(s.odometer) OVER w AS odometer_change_km,
        s.battery_level - LAG(s.battery_level) OVER w AS battery_change
    FROM samples s
    WINDOW w AS (PARTITION BY s.car_id ORDER BY s.date)
),
gaps AS (
    SELECT 'open_drive'::text AS gap_kind,
        c.name AS car_name,
        d.start_date AS started_at,
        NULL::timestamp AS ended_at,
        EXTRACT(EPOCH FROM ((now() AT TIME ZONE 'UTC') - d.start_date)) / 3600.0 AS duration_hours,
        d.id AS record_id,
        NULL::double precision AS odometer_change_km,
        NULL::integer AS battery_change
    FROM drives d
        JOIN scope c ON c.id = d.car_id
    WHERE d.end_date IS NULL
        AND (now() AT TIME ZONE 'UTC') - d.start_date
            >= make_interval(hours => %(min_hours)s::int)
    UNION ALL
    SELECT 'open_charge',
        c.name,
        cp.start_date,
        NULL::timestamp,
        EXTRACT(EPOCH FROM ((now() AT TIME ZONE 'UTC') - cp.start_date)) / 3600.0,
        cp.id,
        NULL,
        NULL
    FROM charging_processes cp
        JOIN scope c ON c.id = cp.car_id
    WHERE cp.end_date IS NULL
        AND (now() AT TIME ZONE 'UTC') - cp.start_date
            >= make_interval(hours => %(min_hours)s::int)
    UNION ALL
    SELECT 'position_hole',
        c.name,
        h.started_at,
        h.ended_at,
        EXTRACT(EPOCH FROM (h.ended_at - h.started_at)) / 3600.0,
        NULL::integer,
        h.odometer_change_km,
        h.battery_change
    FROM holes h
        JOIN scope c ON c.id = h.car_id
    WHERE h.started_at IS NOT NULL
        AND h.ended_at - h.started_at >= make_interval(hours => %(min_hours)s::int)
        AND (h.odometer_change_km >= 0.1 OR h.battery_change >= 1)
)
SELECT gap_kind,
    car_name,
    started_at,
    ended_at,
    ROUND(duration_hours::numeric, 1) AS duration_hours,
    record_id,
    ROUND(odometer_change_km::numeric, 1) AS odometer_change_km,
    battery_change
FROM gaps
ORDER BY duration_hours DESC, started_at DESC
LIMIT %(limit)s::int;
