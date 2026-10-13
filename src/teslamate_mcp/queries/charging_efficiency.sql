WITH sessions AS (
    SELECT cp.id,
        cp.car_id,
        cp.charge_energy_added,
        cp.charge_energy_used,
        -- DC: a sample came from a fast charger, or had no AC phases while
        -- power flowed. AC sessions often end on a 0 kW sample with no phases,
        -- which used to make them count as DC.
        CASE WHEN EXISTS (
            SELECT 1
            FROM charges ch
            WHERE ch.charging_process_id = cp.id
                AND (ch.fast_charger_present OR (ch.charger_phases IS NULL AND ch.charger_power > 0))
        ) THEN 'DC' ELSE 'AC' END AS charge_type
    FROM charging_processes cp
    WHERE cp.charge_energy_used > 0
        AND cp.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
)
SELECT c.name AS car_name,
    s.charge_type,
    COUNT(*) AS sessions,
    ROUND(SUM(s.charge_energy_added)::numeric, 1) AS kwh_added,
    ROUND(SUM(s.charge_energy_used)::numeric, 1) AS kwh_used,
    ROUND((100 * SUM(s.charge_energy_added) / NULLIF(SUM(s.charge_energy_used), 0))::numeric, 1)
        AS efficiency_pct
FROM sessions s
    JOIN cars c ON s.car_id = c.id
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
GROUP BY c.name, s.charge_type
ORDER BY c.name, s.charge_type;
