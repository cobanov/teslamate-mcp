-- Latest position per car via a LATERAL top-1; see battery_health_summary.sql
-- for why the correlated MAX(date) subquery this replaces could not complete
-- on a large positions table.
SELECT c.name as car_name,
    p.battery_level,
    p.rated_battery_range_km,
    p.odometer,
    p.outside_temp,
    p.is_climate_on,
    p.latitude,
    p.longitude,
    a.display_name as location,
    a.city,
    a.state,
    p.date as last_update,
    CASE
        WHEN st.state = 'online' AND drv.start_date IS NOT NULL THEN 'driving'
        WHEN st.state = 'online' AND chg.start_date IS NOT NULL THEN 'charging'
        ELSE st.state
    END AS car_state,
    CASE
        WHEN st.state = 'online' AND drv.start_date IS NOT NULL THEN drv.start_date
        WHEN st.state = 'online' AND chg.start_date IS NOT NULL THEN chg.start_date
        ELSE st.start_date
    END AS car_state_since
FROM cars c
    CROSS JOIN LATERAL (
        SELECT *
        FROM positions p
        WHERE p.car_id = c.id
        ORDER BY p.date DESC
        LIMIT 1
    ) p
    LEFT JOIN LATERAL (
        SELECT *
        FROM addresses a
        ORDER BY (
                (p.latitude - a.latitude) ^ 2 + (p.longitude - a.longitude) ^ 2
            )
        LIMIT 1
    ) a ON true
    LEFT JOIN LATERAL (
        SELECT s.state::text AS state,
            s.start_date
        FROM states s
        WHERE s.car_id = c.id
            AND s.end_date IS NULL
        ORDER BY s.start_date DESC
        LIMIT 1
    ) st ON true
    -- Driving: the latest position belongs to a drive that has not ended, and
    -- is recent. TeslaMate leaves drives open when it restarts mid-drive, so
    -- an open drive alone does not mean the car is moving.
    LEFT JOIN LATERAL (
        SELECT d.start_date
        FROM drives d
        WHERE d.id = p.drive_id
            AND d.end_date IS NULL
            AND p.date >= (now() AT TIME ZONE 'UTC') - interval '30 minutes'
    ) drv ON true
    LEFT JOIN LATERAL (
        SELECT cp.start_date
        FROM charging_processes cp
        WHERE cp.car_id = c.id
            AND cp.end_date IS NULL
            AND cp.start_date >= st.start_date
        ORDER BY cp.start_date DESC
        LIMIT 1
    ) chg ON true
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%');
