SELECT c.name as car_name,
    d.start_date,
    d.distance as distance_km,
    d.duration_min,
    d.speed_max,
    start_addr.display_name as start_location,
    end_addr.display_name as end_location,
    d.outside_temp_avg
FROM drives d
    JOIN cars c ON d.car_id = c.id
    LEFT JOIN addresses start_addr ON d.start_address_id = start_addr.id
    LEFT JOIN addresses end_addr ON d.end_address_id = end_addr.id
ORDER BY d.distance DESC
LIMIT 10;