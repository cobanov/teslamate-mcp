SELECT c.name as car_name,
    COUNT(*) as total_charging_sessions,
    SUM(cp.charge_energy_added) as total_energy_added_kwh,
    AVG(cp.charge_energy_added) as avg_energy_per_session,
    SUM(cp.duration_min) as total_charging_time_min,
    AVG(cp.duration_min) as avg_charging_time_min,
    SUM(COALESCE(cp.cost, 0)) as total_charging_cost
FROM charging_processes cp
    JOIN cars c ON cp.car_id = c.id
GROUP BY c.id,
    c.name
ORDER BY total_energy_added_kwh DESC;