SELECT c.name as car_name,
    EXTRACT(
        DOW
        FROM d.start_date
    ) as day_of_week,
    CASE
        EXTRACT(
            DOW
            FROM d.start_date
        )
        WHEN 0 THEN 'Sunday'
        WHEN 1 THEN 'Monday'
        WHEN 2 THEN 'Tuesday'
        WHEN 3 THEN 'Wednesday'
        WHEN 4 THEN 'Thursday'
        WHEN 5 THEN 'Friday'
        WHEN 6 THEN 'Saturday'
    END as day_name,
    COUNT(*) as trip_count,
    SUM(d.distance) as total_distance_km,
    AVG(d.distance) as avg_distance_km
FROM drives d
    JOIN cars c ON d.car_id = c.id
GROUP BY c.name,
    EXTRACT(
        DOW
        FROM d.start_date
    )
ORDER BY c.name,
    day_of_week;