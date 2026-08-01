SELECT c.name AS car_name,
    COUNT(*) AS samples,
    ROUND(AVG(p.battery_level)::numeric, 1) AS avg_soc,
    ROUND((100.0 * COUNT(*) FILTER (WHERE p.battery_level > 80) / COUNT(*))::numeric, 1)
        AS pct_above_80,
    ROUND((100.0 * COUNT(*) FILTER (WHERE p.battery_level < 20) / COUNT(*))::numeric, 1)
        AS pct_below_20,
    MIN(p.battery_level) AS min_soc,
    MAX(p.battery_level) AS max_soc
FROM positions p
    JOIN cars c ON p.car_id = c.id
WHERE p.battery_level IS NOT NULL
    AND p.date >= CURRENT_DATE - make_interval(days => %(days)s::int)
    AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
GROUP BY c.name
ORDER BY c.name;
