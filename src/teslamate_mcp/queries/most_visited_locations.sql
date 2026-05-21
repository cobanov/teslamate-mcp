SELECT a.display_name as location,
    a.city,
    a.state,
    COUNT(*) as visit_count,
    SUM(d.duration_min) as total_time_spent_min
FROM drives d
    JOIN addresses a ON (
        d.start_address_id = a.id
        OR d.end_address_id = a.id
    )
GROUP BY a.id,
    a.display_name,
    a.city,
    a.state
ORDER BY visit_count DESC
LIMIT 15;