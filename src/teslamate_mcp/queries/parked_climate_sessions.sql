-- Climate sessions while parked, from TeslaMate's polled positions (the
-- streamed ones carry no climate state). Each sample stands for the time
-- until the next one, capped at 10 minutes and at the next drive's start;
-- consecutive climate-on samples less than 15 minutes apart form a session.
-- While parked and unplugged the battery power is the HVAC draw plus a small
-- base load, so energy is that power over time; plugged-in samples draw from
-- the grid and are left out of it.
WITH scope_cars AS (
    SELECT c.id,
        c.name
    FROM cars c
    WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
parks AS (
    SELECT d.car_id,
        d.end_date AS park_start,
        LEAD(d.start_date) OVER (PARTITION BY d.car_id ORDER BY d.start_date) AS park_end,
        d.end_address_id,
        d.end_geofence_id
    FROM drives d
    WHERE d.car_id IN (SELECT id FROM scope_cars)
        AND d.end_date IS NOT NULL
),
samples AS (
    SELECT p.car_id,
        p.date,
        p.is_climate_on,
        p.power,
        p.inside_temp,
        p.outside_temp,
        p.driver_temp_setting,
        pk.park_start,
        pk.park_end,
        pk.end_address_id,
        pk.end_geofence_id,
        LEAD(p.date) OVER w AS next_date,
        LAG(p.date) OVER w AS prev_date,
        LAG(p.is_climate_on) OVER w AS prev_on
    FROM positions p
        JOIN parks pk ON pk.car_id = p.car_id
            AND p.date >= pk.park_start
            AND p.date < COALESCE(pk.park_end, 'infinity')
    WHERE p.drive_id IS NULL
        AND p.is_climate_on IS NOT NULL
        AND p.date >= CURRENT_DATE - make_interval(days => %(days)s::int)
    WINDOW w AS (PARTITION BY p.car_id, pk.park_start ORDER BY p.date)
),
marked AS (
    SELECT s.*,
        LEAST(s.date + interval '10 minutes', COALESCE(s.next_date, 'infinity'),
            COALESCE(s.park_end, 'infinity')) AS credit_end,
        EXISTS (
            SELECT 1
            FROM charging_processes cp
            WHERE cp.car_id = s.car_id
                AND s.date >= cp.start_date
                AND s.date <= COALESCE(cp.end_date, 'infinity')
        ) AS plugged_in,
        CASE WHEN s.prev_on IS DISTINCT FROM s.is_climate_on
                OR s.date - s.prev_date > interval '15 minutes' THEN 1 ELSE 0 END AS new_group
    FROM samples s
),
grouped AS (
    SELECT m.*,
        SUM(m.new_group) OVER (PARTITION BY m.car_id, m.park_start ORDER BY m.date) AS grp
    FROM marked m
),
sessions AS (
    SELECT g.car_id,
        g.park_start,
        MIN(g.park_end) AS park_end,
        MIN(g.end_address_id) AS address_id,
        MIN(g.end_geofence_id) AS geofence_id,
        MIN(g.date) AS start_date,
        MAX(g.credit_end) AS end_date,
        COALESCE(SUM(GREATEST(g.power, 0) * EXTRACT(EPOCH FROM (g.credit_end - g.date)) / 3600.0)
            FILTER (WHERE NOT g.plugged_in), 0) AS kwh,
        BOOL_OR(g.plugged_in) AS plugged_in,
        AVG(g.outside_temp) AS outside_temp,
        AVG(g.inside_temp) AS inside_temp,
        AVG(g.driver_temp_setting) AS setpoint
    FROM grouped g
    WHERE g.is_climate_on
    GROUP BY g.car_id, g.park_start, g.grp
)
SELECT c.name AS car_name,
    s.start_date,
    s.end_date,
    ROUND((EXTRACT(EPOCH FROM (s.end_date - s.start_date)) / 60.0)::numeric) AS minutes,
    CASE
        WHEN s.park_end - s.end_date <= interval '5 minutes' THEN 'before_drive'
        WHEN s.start_date - s.park_start <= interval '5 minutes' THEN 'after_drive'
        ELSE 'parked'
    END AS kind,
    CASE
        WHEN s.outside_temp > s.setpoint THEN 'cooling'
        WHEN s.outside_temp <= s.setpoint THEN 'heating'
    END AS mode,
    ROUND(s.kwh::numeric, 2) AS energy_kwh,
    ROUND((s.kwh / NULLIF(EXTRACT(EPOCH FROM (s.end_date - s.start_date)) / 3600.0, 0))::numeric,
        1) AS avg_power_kw,
    s.plugged_in,
    ROUND(s.outside_temp::numeric, 1) AS outside_temp,
    ROUND(s.inside_temp::numeric, 1) AS inside_temp,
    ROUND(s.setpoint::numeric, 1) AS setpoint,
    COALESCE(g.name, a.display_name) AS location
FROM sessions s
    JOIN scope_cars c ON c.id = s.car_id
    LEFT JOIN geofences g ON g.id = s.geofence_id
    LEFT JOIN addresses a ON a.id = s.address_id
WHERE s.end_date - s.start_date >= make_interval(mins => %(min_minutes)s::int)
ORDER BY s.start_date DESC
LIMIT %(limit)s::int;
