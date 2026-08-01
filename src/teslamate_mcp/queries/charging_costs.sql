SELECT CASE %(group_by)s::text
        WHEN 'month' THEN TO_CHAR(
            DATE_TRUNC('month', (cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text),
            'YYYY-MM'
        )
        WHEN 'location' THEN COALESCE(a.display_name, 'Unknown')
        WHEN 'car' THEN c.name
    END AS group_key,
    COUNT(*) AS sessions,
    ROUND(SUM(cp.charge_energy_added)::numeric, 2) AS total_energy_kwh,
    ROUND(SUM(COALESCE(cp.cost, 0))::numeric, 2) AS total_cost,
    ROUND(
        (SUM(COALESCE(cp.cost, 0)) / NULLIF(SUM(cp.charge_energy_added), 0))::numeric,
        4
    ) AS avg_cost_per_kwh
FROM charging_processes cp
    JOIN cars c ON cp.car_id = c.id
    LEFT JOIN addresses a ON cp.address_id = a.id
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
    AND (%(start_date)s::date IS NULL
        OR ((cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date >= %(start_date)s::date)
    AND (%(end_date)s::date IS NULL
        OR ((cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date <= %(end_date)s::date)
GROUP BY 1
ORDER BY 1;
