-- Latest position per car via a LATERAL top-1.
--
-- The previous form filtered with
--   WHERE p.date = (SELECT MAX(date) FROM positions p2 WHERE p2.car_id = p.car_id)
-- which re-scanned the whole positions table once per candidate row. On a
-- 3M-row table the planner costed that at ~2.6e11 and it never completed.
-- Driving from `cars` also lets the car_name filter cut the set before any
-- positions lookup happens.
SELECT c.name as car_name,
    p.battery_level,
    p.usable_battery_level,
    p.rated_battery_range_km,
    p.ideal_battery_range_km,
    p.est_battery_range_km,
    ROUND(
        (
            p.rated_battery_range_km / NULLIF(p.ideal_battery_range_km, 0) * 100
        )::numeric,
        2
    ) as battery_health_pct
FROM cars c
    CROSS JOIN LATERAL (
        SELECT *
        FROM positions p
        WHERE p.car_id = c.id
        ORDER BY p.date DESC
        LIMIT 1
    ) p
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%');
