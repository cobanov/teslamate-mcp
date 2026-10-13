-- One point per drive for a consumption scatter: outside temperature,
-- average speed, distance, and consumption (rated range used x the car's
-- efficiency). Implausible consumption from range recalibrations is dropped.
SELECT d.id AS drive_id,
    c.name AS car_name,
    d.start_date,
    ROUND(d.outside_temp_avg::numeric, 1) AS outside_temp,
    ROUND(d.distance::numeric, 1) AS distance_km,
    ROUND((d.distance / NULLIF(d.duration_min, 0) * 60)::numeric, 1) AS avg_speed_kmh,
    ROUND(((d.start_rated_range_km - d.end_rated_range_km) * c.efficiency * 1000
        / d.distance)::numeric) AS wh_per_km
FROM drives d
    JOIN cars c ON c.id = d.car_id
WHERE d.end_date IS NOT NULL
    AND d.outside_temp_avg IS NOT NULL
    AND d.distance >= %(min_distance_km)s::float8
    AND (d.start_rated_range_km - d.end_rated_range_km) * c.efficiency * 1000 / d.distance
        BETWEEN 50 AND 600
    AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
    AND d.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
ORDER BY d.start_date DESC
LIMIT %(limit)s::int;
