WITH monthly_stats AS (
    SELECT c.name as car_name,
        DATE_TRUNC('month', d.start_date) as month,
        ROUND(AVG(d.outside_temp_avg)::numeric, 1) as avg_temp,
        SUM(d.distance) as total_distance,
        COUNT(d.id) as drive_count
    FROM drives d
        JOIN cars c ON d.car_id = c.id
    WHERE d.start_date >= CURRENT_DATE - INTERVAL '12 months'
    GROUP BY c.id,
        c.name,
        DATE_TRUNC('month', d.start_date)
)
SELECT car_name,
    month,
    avg_temp,
    ROUND(total_distance::numeric, 2) as total_distance_km,
    drive_count,
    ROUND((total_distance / drive_count)::numeric, 2) as avg_distance_per_drive
FROM monthly_stats
ORDER BY car_name,
    month DESC;