SELECT TO_CHAR(DATE_TRUNC('month', (cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text),
        'YYYY-MM') AS month,
    c.name AS car_name,
    ROUND(AVG(cp.charge_energy_added
        / ((cp.end_battery_level - cp.start_battery_level) / 100.0))::numeric, 1)
        AS avg_est_capacity_kwh,
    ROUND(MIN(cp.charge_energy_added
        / ((cp.end_battery_level - cp.start_battery_level) / 100.0))::numeric, 1)
        AS min_est_capacity_kwh,
    ROUND(MAX(cp.charge_energy_added
        / ((cp.end_battery_level - cp.start_battery_level) / 100.0))::numeric, 1)
        AS max_est_capacity_kwh,
    COUNT(*) AS sessions
FROM charging_processes cp
    JOIN cars c ON cp.car_id = c.id
WHERE cp.end_battery_level - cp.start_battery_level >= %(min_soc_delta)s::int
    AND cp.charge_energy_added > 0
    AND cp.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
    AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
GROUP BY TO_CHAR(DATE_TRUNC('month', (cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s),
        'YYYY-MM'),
    c.name
ORDER BY c.name, month;
