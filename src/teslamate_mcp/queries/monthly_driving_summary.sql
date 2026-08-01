SELECT c.name as car_name,
    DATE_TRUNC('month', (d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text) as month,
    COUNT(*) as total_trips,
    SUM(d.distance) as total_distance_km,
    AVG(d.distance) as avg_trip_distance_km,
    SUM(d.duration_min) as total_driving_time_min,
    AVG(d.outside_temp_avg) as avg_outside_temp,
    MAX(d.speed_max) as max_speed_reached
FROM drives d
    JOIN cars c ON d.car_id = c.id
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
    AND (%(days)s::int IS NULL OR d.start_date >= CURRENT_DATE - make_interval(days => %(days)s))
GROUP BY c.id,
    c.name,
    DATE_TRUNC('month', (d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)
ORDER BY month DESC,
    c.name;