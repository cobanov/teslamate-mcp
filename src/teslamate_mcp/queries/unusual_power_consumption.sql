SELECT c.name as car_name,
    d.start_date,
    d.distance,
    (d.start_rated_range_km - d.end_rated_range_km) as range_used,
    ROUND(
        (
            (d.start_rated_range_km - d.end_rated_range_km) / NULLIF(d.distance, 0) * 100
        )::numeric,
        2
    ) as consumption_pct,
    d.outside_temp_avg,
    start_addr.display_name as start_location,
    end_addr.display_name as end_location
FROM drives d
    JOIN cars c ON d.car_id = c.id
    LEFT JOIN addresses start_addr ON d.start_address_id = start_addr.id
    LEFT JOIN addresses end_addr ON d.end_address_id = end_addr.id
WHERE d.distance > 0
    AND d.start_rated_range_km > d.end_rated_range_km
    AND (
        (d.start_rated_range_km - d.end_rated_range_km) / d.distance * 100
    ) > %(threshold_pct)s::float8 -- consumption above threshold_pct
    AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
    AND (%(days)s::int IS NULL OR d.start_date >= CURRENT_DATE - make_interval(days => %(days)s))
ORDER BY consumption_pct DESC
LIMIT %(limit)s::int;