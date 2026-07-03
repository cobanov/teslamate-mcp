SELECT c.name as car_name,
    DATE_TRUNC('month', (p.date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text) as month,
    ROUND(AVG(p.rated_battery_range_km)::numeric, 1) as avg_rated_range,
    ROUND(MAX(p.rated_battery_range_km)::numeric, 1) as max_rated_range,
    COUNT(*) as data_points
FROM positions p
    JOIN cars c ON p.car_id = c.id
WHERE p.battery_level = 100 -- Only look at full charges
    AND p.date >= CURRENT_DATE - make_interval(days => %(days)s::int)
    AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
GROUP BY c.id,
    c.name,
    DATE_TRUNC('month', (p.date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)
ORDER BY car_name,
    month;
