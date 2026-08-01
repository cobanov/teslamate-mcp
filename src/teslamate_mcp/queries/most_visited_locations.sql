SELECT a.display_name as location,
    a.city,
    a.state,
    COUNT(*) as visit_count,
    SUM(d.duration_min) as total_time_spent_min
FROM drives d
    JOIN cars c ON d.car_id = c.id
    JOIN addresses a ON (
        d.start_address_id = a.id
        OR d.end_address_id = a.id
    )
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
    AND (%(days)s::int IS NULL OR d.start_date >= CURRENT_DATE - make_interval(days => %(days)s))
GROUP BY a.id,
    a.display_name,
    a.city,
    a.state
ORDER BY visit_count DESC
LIMIT %(limit)s::int;