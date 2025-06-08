SELECT DATE(start_date) AS drive_day,
    COUNT(*) AS drive_count,
    SUM(distance) AS total_km,
    SUM(duration_min) AS total_minutes
FROM drives
GROUP BY drive_day
ORDER BY drive_day DESC;