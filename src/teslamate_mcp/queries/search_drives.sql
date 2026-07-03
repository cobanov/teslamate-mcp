SELECT d.id AS drive_id,
    c.name AS car_name,
    d.start_date,
    d.end_date,
    d.distance AS distance_km,
    d.duration_min,
    d.speed_max,
    start_addr.display_name AS start_location,
    start_addr.city AS start_city,
    end_addr.display_name AS end_location,
    end_addr.city AS end_city,
    d.outside_temp_avg,
    (d.start_rated_range_km - d.end_rated_range_km) AS rated_range_used_km
FROM drives d
    JOIN cars c ON d.car_id = c.id
    LEFT JOIN addresses start_addr ON d.start_address_id = start_addr.id
    LEFT JOIN addresses end_addr ON d.end_address_id = end_addr.id
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
    AND (%(start_date)s::date IS NULL
        OR ((d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date >= %(start_date)s::date)
    AND (%(end_date)s::date IS NULL
        OR ((d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date <= %(end_date)s::date)
    AND (%(min_distance_km)s::float8 IS NULL OR d.distance >= %(min_distance_km)s)
    AND (%(max_distance_km)s::float8 IS NULL OR d.distance <= %(max_distance_km)s)
    AND (%(location)s::text IS NULL
        OR start_addr.display_name ILIKE '%%' || %(location)s || '%%'
        OR start_addr.city ILIKE '%%' || %(location)s || '%%'
        OR end_addr.display_name ILIKE '%%' || %(location)s || '%%'
        OR end_addr.city ILIKE '%%' || %(location)s || '%%')
ORDER BY CASE
        WHEN %(order_by)s::text = 'distance' THEN d.distance
        WHEN %(order_by)s::text = 'duration' THEN d.duration_min
    END DESC NULLS LAST,
    d.start_date DESC
LIMIT %(limit)s::int;
