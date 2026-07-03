SELECT c.name as car_name,
    DATE_TRUNC('week', (p.date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text) as week,
    AVG(p.tpms_pressure_fl) as avg_front_left,
    AVG(p.tpms_pressure_fr) as avg_front_right,
    AVG(p.tpms_pressure_rl) as avg_rear_left,
    AVG(p.tpms_pressure_rr) as avg_rear_right,
    AVG(
        (
            p.tpms_pressure_fl + p.tpms_pressure_fr + p.tpms_pressure_rl + p.tpms_pressure_rr
        ) / 4
    ) as weekly_avg_pressure,
    COUNT(*) as readings_count
FROM positions p
    JOIN cars c ON p.car_id = c.id
WHERE p.tpms_pressure_fl IS NOT NULL
    AND p.tpms_pressure_fr IS NOT NULL
    AND p.tpms_pressure_rl IS NOT NULL
    AND p.tpms_pressure_rr IS NOT NULL
    AND p.date >= CURRENT_DATE - make_interval(days => %(days)s::int)
    AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
GROUP BY c.id,
    c.name,
    DATE_TRUNC('week', (p.date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)
ORDER BY week DESC,
    c.name;