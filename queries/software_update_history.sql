SELECT c.name as car_name,
    u.version,
    u.start_date,
    u.end_date,
    EXTRACT(
        EPOCH
        FROM (u.end_date - u.start_date)
    ) / 60 as update_duration_min
FROM updates u
    JOIN cars c ON u.car_id = c.id
ORDER BY u.start_date DESC;