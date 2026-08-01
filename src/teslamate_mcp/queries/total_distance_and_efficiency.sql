SELECT c.name as car_name,
    COUNT(d.id) as total_drives,
    ROUND(SUM(d.distance)::numeric, 2) as total_distance_km,
    ROUND(AVG(d.distance)::numeric, 2) as avg_distance_per_drive,
    ROUND(AVG(d.outside_temp_avg)::numeric, 1) as avg_outside_temp,
    ROUND(AVG(d.speed_max)::numeric, 1) as avg_max_speed
FROM drives d
    JOIN cars c ON d.car_id = c.id
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
    AND (%(days)s::int IS NULL OR d.start_date >= CURRENT_DATE - make_interval(days => %(days)s))
GROUP BY c.id,
    c.name
ORDER BY total_distance_km DESC;