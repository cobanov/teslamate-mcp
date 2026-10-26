-- How the car is driven, per local month: hard accelerations, hard
-- regenerative braking, time above fast_kmh, and how much energy regen
-- recovers, from the power and speed samples TeslaMate logs while driving.
--
-- An event is a run of samples past the power threshold; a new one starts
-- when the previous sample past it is more than 10 s back, so a single long
-- pull or the samples flickering around the threshold count once. Each sample
-- stands for the time until the next one, and gaps over a minute are holes.
WITH scoped_drives AS (
    SELECT d.id,
        d.car_id,
        DATE_TRUNC('month', (d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text) AS month,
        d.distance,
        d.speed_max
    FROM drives d
        JOIN cars c ON c.id = d.car_id
    WHERE d.end_date IS NOT NULL
        AND d.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
samples AS (
    SELECT sd.car_id,
        sd.month,
        p.drive_id,
        p.date,
        p.speed,
        p.power,
        EXTRACT(EPOCH FROM (
            LEAD(p.date) OVER (PARTITION BY p.drive_id ORDER BY p.date) - p.date
        ))::float8 AS dt
    FROM scoped_drives sd
        JOIN positions p ON p.drive_id = sd.id
    WHERE p.power IS NOT NULL
),
accel AS (
    SELECT car_id,
        month,
        date - LAG(date) OVER (PARTITION BY drive_id ORDER BY date) AS gap
    FROM samples
    WHERE power >= %(accel_kw)s::int
),
regen AS (
    SELECT car_id,
        month,
        date - LAG(date) OVER (PARTITION BY drive_id ORDER BY date) AS gap
    FROM samples
    WHERE power <= -%(regen_kw)s::int
),
events AS (
    SELECT car_id, month, COUNT(*) FILTER (WHERE kind = 'accel') AS accel_events,
        COUNT(*) FILTER (WHERE kind = 'regen') AS regen_events
    FROM (
        SELECT car_id, month, 'accel' AS kind FROM accel
        WHERE gap IS NULL OR gap > INTERVAL '10 seconds'
        UNION ALL
        SELECT car_id, month, 'regen' FROM regen
        WHERE gap IS NULL OR gap > INTERVAL '10 seconds'
    ) e
    GROUP BY car_id, month
),
energy AS (
    SELECT car_id,
        month,
        SUM(dt) FILTER (WHERE speed > 0) AS moving_s,
        SUM(dt) FILTER (WHERE speed > %(fast_kmh)s::int) AS fast_s,
        SUM(power * dt) FILTER (WHERE power > 0) / 3600 AS used_kwh,
        -SUM(power * dt) FILTER (WHERE power < 0) / 3600 AS recovered_kwh
    FROM samples
    WHERE dt > 0
        AND dt <= 60
    GROUP BY car_id, month
),
totals AS (
    SELECT car_id, month, COUNT(*) AS drives, SUM(distance) AS km, MAX(speed_max) AS speed_max
    FROM scoped_drives
    GROUP BY car_id, month
),
rated AS (
    SELECT t.car_id,
        t.month,
        t.drives,
        t.km,
        t.speed_max,
        e.moving_s,
        COALESCE(ev.accel_events, 0) * 100 / NULLIF(t.km, 0) AS accel_per_100km,
        COALESCE(ev.regen_events, 0) * 100 / NULLIF(t.km, 0) AS regen_per_100km,
        100 * e.fast_s / NULLIF(e.moving_s, 0) AS fast_pct,
        100 * e.recovered_kwh / NULLIF(e.used_kwh, 0) AS regen_share_pct
    FROM totals t
        JOIN energy e ON e.car_id = t.car_id AND e.month = t.month
        LEFT JOIN events ev ON ev.car_id = t.car_id AND ev.month = t.month
)
SELECT TO_CHAR(r.month, 'YYYY-MM') AS month,
    c.name AS car_name,
    r.drives,
    ROUND(r.km::numeric, 1) AS distance_km,
    ROUND((r.moving_s / 3600)::numeric, 1) AS moving_hours,
    ROUND(r.accel_per_100km::numeric, 1) AS hard_accel_per_100km,
    ROUND(r.regen_per_100km::numeric, 1) AS hard_regen_per_100km,
    ROUND(COALESCE(r.fast_pct, 0)::numeric, 1) AS over_fast_pct,
    r.speed_max AS max_speed_kmh,
    ROUND(r.regen_share_pct::numeric, 1) AS regen_share_pct,
    -- 100 minus capped penalties; null under 50 km, where a few events swing it.
    CASE WHEN r.km >= 50 THEN
        ROUND((100
            - LEAST(40, 0.5 * r.accel_per_100km)
            - LEAST(30, 0.25 * r.regen_per_100km)
            - LEAST(30, 0.5 * COALESCE(r.fast_pct, 0)))::numeric)
    END AS style_score
FROM rated r
    JOIN cars c ON c.id = r.car_id
ORDER BY c.name, r.month DESC;
