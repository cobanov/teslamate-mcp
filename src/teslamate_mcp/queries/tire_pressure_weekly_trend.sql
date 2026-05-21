SELECT c.name as car_name,
    DATE_TRUNC('week', p.date) as week,
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
    AND p.date >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY c.id,
    c.name,
    DATE_TRUNC('week', p.date)
ORDER BY week DESC,
    c.name;