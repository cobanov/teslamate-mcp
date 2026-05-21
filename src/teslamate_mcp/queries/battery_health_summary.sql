SELECT c.name as car_name,
    p.battery_level,
    p.usable_battery_level,
    p.rated_battery_range_km,
    p.ideal_battery_range_km,
    p.est_battery_range_km,
    ROUND(
        (
            p.rated_battery_range_km / NULLIF(p.ideal_battery_range_km, 0) * 100
        ),
        2
    ) as battery_health_pct
FROM positions p
    JOIN cars c ON p.car_id = c.id
WHERE p.date = (
        SELECT MAX(date)
        FROM positions p2
        WHERE p2.car_id = p.car_id
    );