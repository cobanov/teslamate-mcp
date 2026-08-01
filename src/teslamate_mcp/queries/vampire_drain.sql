WITH parked AS (
    SELECT d.car_id,
        d.end_date AS gap_start,
        LEAD(d.start_date) OVER (PARTITION BY d.car_id ORDER BY d.start_date) AS gap_end,
        d.end_rated_range_km,
        LEAD(d.start_rated_range_km) OVER (PARTITION BY d.car_id ORDER BY d.start_date)
            AS next_start_rated_range_km,
        d.end_address_id
    FROM drives d
)
SELECT c.name AS car_name,
    p.gap_start,
    p.gap_end,
    ROUND((EXTRACT(EPOCH FROM (p.gap_end - p.gap_start)) / 3600.0)::numeric, 1) AS gap_hours,
    ROUND((p.end_rated_range_km - p.next_start_rated_range_km)::numeric, 1) AS range_loss_km,
    ROUND(((p.end_rated_range_km - p.next_start_rated_range_km)
        / NULLIF(EXTRACT(EPOCH FROM (p.gap_end - p.gap_start)) / 3600.0, 0))::numeric, 2)
        AS loss_km_per_hour,
    a.display_name AS location
FROM parked p
    JOIN cars c ON p.car_id = c.id
    LEFT JOIN addresses a ON p.end_address_id = a.id
WHERE p.gap_end IS NOT NULL
    AND EXTRACT(EPOCH FROM (p.gap_end - p.gap_start)) / 3600.0 >= %(min_gap_hours)s::float8
    AND p.end_rated_range_km - p.next_start_rated_range_km >= 0
    -- Inclusive overlap: a charge starting exactly when the next drive starts
    -- (or ending exactly when the gap begins) still disqualifies the gap.
    AND NOT EXISTS (
        SELECT 1
        FROM charging_processes cp
        WHERE cp.car_id = p.car_id
            AND cp.start_date <= p.gap_end
            AND COALESCE(cp.end_date, now()) >= p.gap_start
    )
    AND p.gap_start >= CURRENT_DATE - make_interval(days => %(days)s::int)
    AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
ORDER BY range_loss_km DESC
LIMIT %(limit)s::int;
