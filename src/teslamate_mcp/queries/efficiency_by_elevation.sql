-- Consumption by how much a drive climbed: drives are grouped by their net
-- climb per km (TeslaMate's ascent minus descent over the distance). Net
-- climb, not total ascent: GPS elevation noise adds metres of fake ascent and
-- descent on every drive, and they cancel out in the difference.
WITH drives_scoped AS (
    SELECT c.name AS car_name,
        d.distance,
        (d.start_rated_range_km - d.end_rated_range_km) * c.efficiency AS kwh,
        (d.ascent - d.descent) / d.distance AS net_climb_m_per_km,
        d.ascent / d.distance AS ascent_m_per_km
    FROM drives d
        JOIN cars c ON c.id = d.car_id
    WHERE d.end_date IS NOT NULL
        AND d.distance >= %(min_distance_km)s::float8
        AND d.ascent IS NOT NULL
        AND d.descent IS NOT NULL
        AND d.start_rated_range_km IS NOT NULL
        AND d.end_rated_range_km IS NOT NULL
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
        AND (%(days)s::int IS NULL
            OR d.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int))
),
bucketed AS (
    SELECT ds.*,
        CASE
            WHEN ds.net_climb_m_per_km < -10 THEN 1
            WHEN ds.net_climb_m_per_km < -3 THEN 2
            WHEN ds.net_climb_m_per_km <= 3 THEN 3
            WHEN ds.net_climb_m_per_km <= 10 THEN 4
            ELSE 5
        END AS bucket
    FROM drives_scoped ds
),
grouped AS (
    SELECT car_name,
        bucket,
        COUNT(*) AS drives,
        SUM(distance) AS km,
        SUM(kwh) * 1000 / NULLIF(SUM(distance), 0) AS wh_per_km,
        SUM(net_climb_m_per_km * distance) / NULLIF(SUM(distance), 0) AS net_climb_m_per_km,
        SUM(ascent_m_per_km * distance) / NULLIF(SUM(distance), 0) AS ascent_m_per_km
    FROM bucketed
    GROUP BY car_name, bucket
)
SELECT g.car_name,
    CASE g.bucket
        WHEN 1 THEN 'downhill (more than 10 m/km)'
        WHEN 2 THEN 'slight downhill (3-10 m/km)'
        WHEN 3 THEN 'flat (within 3 m/km)'
        WHEN 4 THEN 'slight uphill (3-10 m/km)'
        ELSE 'uphill (more than 10 m/km)'
    END AS climb,
    g.drives,
    ROUND(g.km::numeric, 1) AS distance_km,
    ROUND(g.net_climb_m_per_km::numeric, 1) AS avg_net_climb_m_per_km,
    ROUND(g.ascent_m_per_km::numeric, 1) AS avg_ascent_m_per_km,
    ROUND(g.wh_per_km::numeric) AS wh_per_km,
    ROUND((100 * (g.wh_per_km / NULLIF(flat.wh_per_km, 0) - 1))::numeric, 1) AS vs_flat_pct
FROM grouped g
    LEFT JOIN grouped flat ON flat.car_name = g.car_name AND flat.bucket = 3
ORDER BY g.car_name, g.bucket;
