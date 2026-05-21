SELECT c.name as car_name,
    CASE
        WHEN d.outside_temp_avg < 0 THEN 'Below 0°C'
        WHEN d.outside_temp_avg BETWEEN 0 AND 10 THEN '0-10°C'
        WHEN d.outside_temp_avg BETWEEN 10 AND 20 THEN '10-20°C'
        WHEN d.outside_temp_avg BETWEEN 20 AND 30 THEN '20-30°C'
        ELSE 'Above 30°C'
    END as temp_range,
    COUNT(*) as trip_count,
    AVG(d.distance) as avg_distance_km,
    AVG(
        (d.start_rated_range_km - d.end_rated_range_km) / NULLIF(d.distance, 0) * 100
    ) as avg_consumption_pct
FROM drives d
    JOIN cars c ON d.car_id = c.id
WHERE d.distance > 0
    AND d.start_rated_range_km > d.end_rated_range_km
    AND d.outside_temp_avg IS NOT NULL
GROUP BY c.name,
    CASE
        WHEN d.outside_temp_avg < 0 THEN 'Below 0°C'
        WHEN d.outside_temp_avg BETWEEN 0 AND 10 THEN '0-10°C'
        WHEN d.outside_temp_avg BETWEEN 10 AND 20 THEN '10-20°C'
        WHEN d.outside_temp_avg BETWEEN 20 AND 30 THEN '20-30°C'
        ELSE 'Above 30°C'
    END
ORDER BY c.name,
    avg_consumption_pct;