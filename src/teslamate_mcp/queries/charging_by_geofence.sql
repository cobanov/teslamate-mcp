SELECT COALESCE(g.name, 'Ungeofenced') AS geofence,
    COUNT(*) AS sessions,
    COUNT(*) FILTER (WHERE cp.cost IS NULL) AS sessions_without_cost,
    ROUND(SUM(cp.charge_energy_added)::numeric, 1) AS kwh_added,
    SUM(cp.cost) AS total_cost,
    -- Over costed sessions only; see charging_costs.sql.
    ROUND(
        SUM(cp.cost)
            / NULLIF(SUM(cp.charge_energy_added) FILTER (WHERE cp.cost IS NOT NULL)::numeric, 0),
        3
    ) AS avg_cost_per_kwh
FROM charging_processes cp
    JOIN cars c ON cp.car_id = c.id
    LEFT JOIN geofences g ON cp.geofence_id = g.id
WHERE cp.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
    AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
GROUP BY COALESCE(g.name, 'Ungeofenced')
ORDER BY kwh_added DESC;
