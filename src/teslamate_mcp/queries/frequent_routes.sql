-- The routes a car drives again and again: drives grouped by where they
-- start and end. TeslaMate resolves parking spots a few metres apart to
-- different addresses, so a place here is a geofence when the drive has one,
-- and otherwise a grid cell about twice place_radius_m across around the
-- drive's first or last position.
WITH grid AS (
    -- Cell height in degrees of latitude.
    SELECT 2.0 * %(place_radius_m)s::float8 / 111320.0 AS dlat
),
ends AS (
    SELECT d.id,
        d.car_id,
        c.name AS car_name,
        d.start_date,
        d.distance,
        d.duration_min,
        (d.start_rated_range_km - d.end_rated_range_km) * c.efficiency AS kwh,
        EXTRACT(HOUR FROM (d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::int
            AS departure_hour,
        d.start_address_id,
        d.end_address_id,
        d.start_geofence_id,
        d.end_geofence_id,
        FLOOR(sp.latitude / g.dlat) AS s_row,
        sp.longitude AS s_lon,
        FLOOR(ep.latitude / g.dlat) AS e_row,
        ep.longitude AS e_lon,
        g.dlat
    FROM drives d
        JOIN cars c ON c.id = d.car_id
        JOIN positions sp ON sp.id = d.start_position_id
        JOIN positions ep ON ep.id = d.end_position_id
        CROSS JOIN grid g
    WHERE d.end_date IS NOT NULL
        AND d.duration_min > 0
        AND d.distance >= %(min_distance_km)s::float8
        AND d.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
-- A cell is as wide as it is high: its span in degrees of longitude grows
-- with the latitude of its row, so every position in a row uses one width.
keyed AS (
    SELECT e.*,
        COALESCE('g' || e.start_geofence_id, 'c' || e.s_row || ':' || FLOOR(
            e.s_lon / (e.dlat / GREATEST(COS(RADIANS(e.s_row * e.dlat)), 0.01))
        )) AS s_key,
        COALESCE('g' || e.end_geofence_id, 'c' || e.e_row || ':' || FLOOR(
            e.e_lon / (e.dlat / GREATEST(COS(RADIANS(e.e_row * e.dlat)), 0.01))
        )) AS e_key
    FROM ends e
),
-- A place is called by its geofence, or by the address most drives there
-- resolved to.
place_names AS (
    SELECT x.place_key,
        COALESCE(MAX(gf.name), MODE() WITHIN GROUP (ORDER BY a.display_name)) AS name
    FROM (
        SELECT s_key AS place_key, start_address_id AS address_id,
            start_geofence_id AS geofence_id
        FROM keyed
        UNION ALL
        SELECT e_key, end_address_id, end_geofence_id
        FROM keyed
    ) x
        LEFT JOIN addresses a ON a.id = x.address_id
        LEFT JOIN geofences gf ON gf.id = x.geofence_id
    GROUP BY x.place_key
),
named AS (
    SELECT k.*,
        sn.name AS start_location,
        en.name AS end_location,
        COUNT(*) OVER (PARTITION BY k.car_id, k.s_key, k.e_key) AS route_drives
    FROM keyed k
        JOIN place_names sn ON sn.place_key = k.s_key
        JOIN place_names en ON en.place_key = k.e_key
    WHERE k.s_key <> k.e_key
        AND (%(start_location)s::text IS NULL
            OR sn.name ILIKE '%%' || %(start_location)s || '%%')
        AND (%(end_location)s::text IS NULL
            OR en.name ILIKE '%%' || %(end_location)s || '%%')
),
-- limit counts routes, so a route keeps all its hours with by_departure_hour.
ranked AS (
    SELECT n.*,
        CASE WHEN %(by_departure_hour)s::boolean THEN n.departure_hour END AS hour_key,
        DENSE_RANK() OVER (ORDER BY n.route_drives DESC, n.car_id, n.s_key, n.e_key) AS route_rank
    FROM named n
    WHERE n.route_drives >= %(min_drives)s::int
)
SELECT r.car_name,
    r.start_location,
    r.end_location,
    r.hour_key AS departure_hour,
    COUNT(*) AS drives,
    ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.distance))::numeric, 1)
        AS typical_distance_km,
    ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.duration_min))::numeric)
        AS typical_duration_min,
    MIN(r.duration_min) AS fastest_duration_min,
    MAX(r.duration_min) AS slowest_duration_min,
    ROUND((SUM(r.distance) / SUM(r.duration_min) * 60)::numeric, 1) AS avg_speed_kmh,
    -- Implausible consumption (range recalibrations) stays out of the average.
    ROUND((SUM(r.kwh) FILTER (WHERE r.kwh * 1000 / r.distance BETWEEN 50 AND 600) * 1000
        / NULLIF(SUM(r.distance) FILTER (WHERE r.kwh * 1000 / r.distance BETWEEN 50 AND 600), 0)
    )::numeric) AS wh_per_km,
    ROUND(SUM(r.distance)::numeric, 1) AS total_distance_km,
    LPAD((MODE() WITHIN GROUP (ORDER BY r.departure_hour))::text, 2, '0') || ':00'
        AS usual_departure_local,
    (ARRAY_AGG(r.id ORDER BY r.duration_min, r.start_date DESC))[1] AS fastest_drive_id,
    (ARRAY_AGG(r.id ORDER BY r.duration_min DESC, r.start_date DESC))[1] AS slowest_drive_id,
    MAX(r.start_date) AS last_drive
FROM ranked r
WHERE r.route_rank <= %(limit)s::int
GROUP BY r.route_rank,
    r.car_name,
    r.start_location,
    r.end_location,
    r.hour_key
ORDER BY r.route_rank,
    r.hour_key;
