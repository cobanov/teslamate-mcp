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
    p.date as last_update
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
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%');
