-- Consumption by speed, from the samples TeslaMate logs while driving. Each
-- sample stands for the time until the next one in the same drive: its energy
-- is power x time and its distance speed x time. This is power at the battery
-- while moving, not the rated-range scale the drive-level tools use, so the
-- bands compare with each other rather than with those figures.
WITH samples AS (
    SELECT d.car_id,
        p.speed,
        p.power,
        d.outside_temp_avg,
        EXTRACT(EPOCH FROM (
            LEAD(p.date) OVER (PARTITION BY p.drive_id ORDER BY p.date) - p.date
        ))::float8 AS dt
    FROM drives d
        JOIN cars c ON c.id = d.car_id
        JOIN positions p ON p.drive_id = d.id
    WHERE d.end_date IS NOT NULL
        AND d.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
        AND (%(outside_temp_c)s::float8 IS NULL
            OR ABS(d.outside_temp_avg - %(outside_temp_c)s::float8) <= 5)
        AND p.speed IS NOT NULL
        AND p.power IS NOT NULL
),
-- Gaps over a minute are logging holes, not driving. Under 10 km/h the car is
-- crawling or stopped, and the energy per km says nothing about speed. The
-- top band is open-ended.
grouped AS (
    SELECT s.car_id,
        LEAST(s.speed / %(band_kmh)s::int, 150 / %(band_kmh)s::int) * %(band_kmh)s::int
            AS speed_from,
        SUM(s.speed * s.dt) / 3600 AS km,
        SUM(s.dt) / 3600 AS hours,
        SUM(s.power * s.dt) * 1000 / NULLIF(SUM(s.speed * s.dt), 0) AS wh_per_km,
        SUM(s.outside_temp_avg * s.speed * s.dt)
            / NULLIF(SUM(s.speed * s.dt) FILTER (WHERE s.outside_temp_avg IS NOT NULL), 0)
            AS outside_temp
    FROM samples s
    WHERE s.dt > 0
        AND s.dt <= 60
        AND s.speed >= 10
    GROUP BY s.car_id, 2
    HAVING SUM(s.speed * s.dt) >= 3600
)
SELECT c.name AS car_name,
    CASE
        WHEN g.speed_from >= 150 / %(band_kmh)s::int * %(band_kmh)s::int
            THEN g.speed_from || '+ km/h'
        ELSE g.speed_from || '-' || (g.speed_from + %(band_kmh)s::int) || ' km/h'
    END AS speed_band,
    g.speed_from AS speed_from_kmh,
    ROUND(g.km::numeric, 1) AS distance_km,
    ROUND(g.hours::numeric, 2) AS hours,
    ROUND(g.wh_per_km::numeric) AS wh_per_km,
    -- Against the car's most efficient band with at least 20 km behind it.
    ROUND((100 * (g.wh_per_km / NULLIF(MIN(g.wh_per_km) FILTER (WHERE g.km >= 20)
        OVER (PARTITION BY g.car_id), 0) - 1))::numeric, 1) AS vs_best_pct,
    ROUND(g.outside_temp::numeric, 1) AS avg_outside_temp
FROM grouped g
    JOIN cars c ON c.id = g.car_id
ORDER BY c.name, g.speed_from;
