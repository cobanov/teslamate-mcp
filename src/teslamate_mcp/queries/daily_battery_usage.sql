SELECT c.name as car_name,
    DATE(p.date) as date,
    MIN(p.battery_level) as min_battery,
    MAX(p.battery_level) as max_battery,
    MAX(p.battery_level) - MIN(p.battery_level) as daily_usage
FROM positions p
    JOIN cars c ON p.car_id = c.id
WHERE p.date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY c.id,
    c.name,
    DATE(p.date)
HAVING MAX(p.battery_level) - MIN(p.battery_level) > 5 -- Filter out days with minimal usage
ORDER BY car_name,
    date DESC;