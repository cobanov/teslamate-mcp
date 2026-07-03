SELECT d.id AS drive_id,
    c.name AS car_name,
    d.start_date,
    d.end_date,
    d.distance AS distance_km,
    d.duration_min,
    ROUND((d.distance / NULLIF(d.duration_min, 0) * 60)::numeric, 1) AS avg_speed_kmh,
    d.speed_max,
    d.power_max,
    d.power_min,
    d.inside_temp_avg,
    d.outside_temp_avg,
    d.start_km AS odometer_start_km,
    d.end_km AS odometer_end_km,
    d.start_rated_range_km,
    d.end_rated_range_km,
    (d.start_rated_range_km - d.end_rated_range_km) AS rated_range_used_km,
    ROUND(
        ((d.start_rated_range_km - d.end_rated_range_km) / NULLIF(d.distance, 0) * 100)::numeric,
        1
    ) AS consumption_pct,
    start_addr.display_name AS start_location,
    start_addr.city AS start_city,
    end_addr.display_name AS end_location,
    end_addr.city AS end_city
FROM drives d
    JOIN cars c ON d.car_id = c.id
    LEFT JOIN addresses start_addr ON d.start_address_id = start_addr.id
    LEFT JOIN addresses end_addr ON d.end_address_id = end_addr.id
WHERE d.id = %(drive_id)s::int;
