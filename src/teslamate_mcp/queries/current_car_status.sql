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
FROM positions p
    JOIN cars c ON p.car_id = c.id
    LEFT JOIN LATERAL (
        SELECT *
        FROM addresses a
        ORDER BY (
                (p.latitude - a.latitude) ^ 2 + (p.longitude - a.longitude) ^ 2
            )
        LIMIT 1
    ) a ON true
WHERE p.date = (
        SELECT MAX(date)
        FROM positions p2
        WHERE p2.car_id = p.car_id
    );