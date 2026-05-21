SELECT c.name as car_name,
    DATE_TRUNC('month', p.date) as month,
    ROUND(AVG(p.rated_battery_range_km)::numeric, 1) as avg_rated_range,
    ROUND(MAX(p.rated_battery_range_km)::numeric, 1) as max_rated_range,
    COUNT(*) as data_points
FROM positions p
    JOIN cars c ON p.car_id = c.id
WHERE p.battery_level = 100 -- Only look at 100% charge
    AND p.date >= CURRENT_DATE - INTERVAL '24 months'
GROUP BY c.id,
    c.name,
    DATE_TRUNC('month', p.date)
ORDER BY car_name,
    month;