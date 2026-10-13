-- Estimate the energy and battery a drive of a given length will take, from
-- the car's own history. Everything is on TeslaMate's rated-range scale:
-- a drive used (rated range lost) x cars.efficiency kWh, and one battery percent
-- is worth (rated km per percent) x cars.efficiency kWh, so the two cancel cleanly.
WITH scope_cars AS (
    SELECT c.id,
        c.name,
        c.efficiency
    FROM cars c
    WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
-- Past drives, tiered by how close their temperature was to the forecast.
-- Drives with implausible consumption (range recalibrations, GPS gaps) are
-- dropped; highway mode keeps only long drives averaging 70 km/h or more.
history AS (
    SELECT d.car_id,
        d.distance,
        (d.start_rated_range_km - d.end_rated_range_km) * c.efficiency AS kwh,
        (d.start_rated_range_km - d.end_rated_range_km) * c.efficiency * 1000 / d.distance
            AS wh_per_km,
        CASE
            WHEN %(outside_temp_c)s::float8 IS NULL THEN 4
            WHEN ABS(d.outside_temp_avg - %(outside_temp_c)s::float8) <= 3 THEN 1
            WHEN ABS(d.outside_temp_avg - %(outside_temp_c)s::float8) <= 6 THEN 2
            WHEN ABS(d.outside_temp_avg - %(outside_temp_c)s::float8) <= 10 THEN 3
            ELSE 4
        END AS tier
    FROM drives d
        JOIN scope_cars c ON c.id = d.car_id
    WHERE d.end_date IS NOT NULL
        AND d.start_date >= (now() AT TIME ZONE 'UTC') - make_interval(days => %(days)s::int)
        AND d.distance >= CASE WHEN %(highway)s::boolean THEN 20 ELSE 5 END
        AND (NOT %(highway)s::boolean OR d.distance / NULLIF(d.duration_min, 0) * 60 >= 70)
        AND (d.start_rated_range_km - d.end_rated_range_km) * c.efficiency * 1000 / d.distance
            BETWEEN 50 AND 600
),
-- The closest temperature tier with enough history (5 drives, 50 km).
chosen AS (
    SELECT car_id,
        MIN(tier) AS tier
    FROM (
        SELECT car_id,
            tier,
            SUM(COUNT(*)) OVER (PARTITION BY car_id ORDER BY tier) AS cum_drives,
            SUM(SUM(distance)) OVER (PARTITION BY car_id ORDER BY tier) AS cum_km
        FROM history
        GROUP BY car_id, tier
    ) t
    WHERE cum_drives >= 5
        AND cum_km >= 50
    GROUP BY car_id
),
stats AS (
    SELECT h.car_id,
        COALESCE(ch.tier, 4) AS tier,
        COUNT(*) AS drives,
        SUM(h.distance) AS km,
        SUM(h.kwh) * 1000 / NULLIF(SUM(h.distance), 0) AS wh_expected,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY h.wh_per_km) AS wh_conservative
    FROM history h
        LEFT JOIN chosen ch ON ch.car_id = h.car_id
    WHERE h.tier <= COALESCE(ch.tier, 4)
    GROUP BY h.car_id, COALESCE(ch.tier, 4)
),
-- Rated km per battery percent, the median over the last 10 charges that
-- added at least 20 percent.
capacity AS (
    SELECT c.id AS car_id,
        PERCENTILE_CONT(0.5) WITHIN GROUP (
            ORDER BY (cp.end_rated_range_km - cp.start_rated_range_km)
                / (cp.end_battery_level - cp.start_battery_level)
        ) AS km_per_pct
    FROM scope_cars c
        CROSS JOIN LATERAL (
            SELECT cp.start_rated_range_km,
                cp.end_rated_range_km,
                cp.start_battery_level,
                cp.end_battery_level
            FROM charging_processes cp
            WHERE cp.car_id = c.id
                AND cp.end_date IS NOT NULL
                AND cp.end_battery_level - cp.start_battery_level >= 20
                AND cp.end_rated_range_km > cp.start_rated_range_km
            ORDER BY cp.start_date DESC
            LIMIT 10
        ) cp
    GROUP BY c.id
),
latest AS (
    SELECT c.id AS car_id,
        p.battery_level,
        p.date
    FROM scope_cars c
        LEFT JOIN LATERAL (
            SELECT p.battery_level,
                p.date
            FROM positions p
            WHERE p.car_id = c.id
                AND p.ideal_battery_range_km IS NOT NULL
                AND p.battery_level IS NOT NULL
            ORDER BY p.date DESC
            LIMIT 1
        ) p ON TRUE
),
estimate AS (
    SELECT c.name AS car_name,
        st.tier,
        st.drives,
        st.km,
        st.wh_expected,
        st.wh_conservative,
        c.efficiency * cap.km_per_pct AS kwh_per_pct,
        COALESCE(%(start_soc)s::int, lt.battery_level) AS start_soc,
        CASE WHEN %(start_soc)s::int IS NULL THEN lt.date END AS start_soc_as_of,
        %(distance_km)s::float8 * st.wh_expected / 1000 AS kwh_expected,
        %(distance_km)s::float8 * st.wh_conservative / 1000 AS kwh_conservative
    FROM scope_cars c
        LEFT JOIN stats st ON st.car_id = c.id
        LEFT JOIN capacity cap ON cap.car_id = c.id
        LEFT JOIN latest lt ON lt.car_id = c.id
)
SELECT e.car_name,
    %(distance_km)s::float8 AS distance_km,
    %(outside_temp_c)s::float8 AS outside_temp_c,
    CASE e.tier
        WHEN 1 THEN 'drives within 3°C'
        WHEN 2 THEN 'drives within 6°C'
        WHEN 3 THEN 'drives within 10°C'
        ELSE 'drives at all temperatures'
    END AS based_on,
    %(highway)s::boolean AS highway,
    COALESCE(e.drives, 0) AS drives_used,
    ROUND(e.km::numeric) AS km_used,
    ROUND(e.wh_expected::numeric) AS wh_per_km_expected,
    ROUND(e.wh_conservative::numeric) AS wh_per_km_conservative,
    ROUND(e.kwh_expected::numeric, 1) AS energy_needed_kwh,
    ROUND(e.kwh_conservative::numeric, 1) AS energy_needed_kwh_conservative,
    ROUND((e.kwh_per_pct * 100)::numeric, 1) AS usable_capacity_kwh,
    ROUND((e.kwh_per_pct * 100 * 1000 / e.wh_expected)::numeric) AS full_battery_range_km,
    e.start_soc,
    e.start_soc_as_of,
    ROUND((e.kwh_expected / e.kwh_per_pct)::numeric, 1) AS soc_needed_pct,
    ROUND((e.kwh_conservative / e.kwh_per_pct)::numeric, 1) AS soc_needed_pct_conservative,
    ROUND((e.start_soc - e.kwh_expected / e.kwh_per_pct)::numeric, 1) AS arrival_soc_pct,
    ROUND((e.start_soc - e.kwh_conservative / e.kwh_per_pct)::numeric, 1)
        AS arrival_soc_pct_conservative
FROM estimate e
ORDER BY e.car_name;
