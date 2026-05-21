SELECT a.display_name as location,
    a.city,
    COUNT(*) as sessions,
    SUM(cp.charge_energy_added) as total_kwh,
    AVG(cp.charge_energy_added) as avg_kwh_per_session,
    SUM(cp.duration_min) as total_minutes,
    SUM(COALESCE(cp.cost, 0)) as total_cost
FROM charging_processes cp
    JOIN addresses a ON cp.address_id = a.id
GROUP BY a.id,
    a.display_name,
    a.city
ORDER BY sessions DESC;