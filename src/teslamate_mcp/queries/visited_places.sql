-- Where the car parks: one row per address it arrived at (a drive ending
-- there), with its coordinates for a map, the number of arrivals, the time
-- parked there (until the car's next drive), and the charging done there.
WITH scope_drives AS (
    SELECT d.car_id,
        d.end_date,
        d.end_address_id,
        d.end_geofence_id,
        LEAD(d.start_date) OVER (PARTITION BY d.car_id ORDER BY d.start_date) AS next_start
    FROM drives d
        JOIN cars c ON c.id = d.car_id
    WHERE d.end_date IS NOT NULL
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
arrivals AS (
    SELECT sd.end_address_id AS address_id,
        COUNT(*) AS arrivals,
        -- The latest arrival is still parked: count it up to now.
        SUM(EXTRACT(EPOCH FROM (
            COALESCE(sd.next_start, now() AT TIME ZONE 'UTC') - sd.end_date
        ))) / 3600.0 AS parked_hours,
        MAX(g.name) AS geofence,
        MAX(sd.end_date) AS last_arrival
    FROM scope_drives sd
        LEFT JOIN geofences g ON g.id = sd.end_geofence_id
    WHERE sd.end_address_id IS NOT NULL
        AND (%(days)s::int IS NULL
            OR sd.end_date >= CURRENT_DATE - make_interval(days => %(days)s::int))
    GROUP BY sd.end_address_id
),
charging AS (
    SELECT cp.address_id,
        COUNT(*) AS sessions,
        SUM(cp.charge_energy_added) AS kwh_added
    FROM charging_processes cp
        JOIN cars c ON c.id = cp.car_id
    WHERE cp.end_date IS NOT NULL
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
        AND (%(days)s::int IS NULL
            OR cp.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int))
    GROUP BY cp.address_id
)
SELECT COALESCE(ar.geofence, a.display_name) AS location,
    a.city,
    ROUND(a.latitude::numeric, 5) AS latitude,
    ROUND(a.longitude::numeric, 5) AS longitude,
    ar.arrivals,
    ROUND(ar.parked_hours::numeric, 1) AS parked_hours,
    COALESCE(ch.sessions, 0) AS charging_sessions,
    ROUND(COALESCE(ch.kwh_added, 0)::numeric, 1) AS kwh_added,
    ar.last_arrival
FROM arrivals ar
    JOIN addresses a ON a.id = ar.address_id
    LEFT JOIN charging ch ON ch.address_id = ar.address_id
WHERE ar.arrivals >= %(min_arrivals)s::int
    AND a.latitude IS NOT NULL
    AND a.longitude IS NOT NULL
ORDER BY ar.arrivals DESC,
    ar.parked_hours DESC
LIMIT %(limit)s::int;
