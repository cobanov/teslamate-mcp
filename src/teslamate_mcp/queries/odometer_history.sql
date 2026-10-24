-- The odometer at the end of each local month, from the drives that month.
-- Months without a drive are left out; the odometer did not move in them.
SELECT TO_CHAR(DATE_TRUNC('month', (d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text),
        'YYYY-MM') AS month,
    c.name AS car_name,
    ROUND(MIN(d.start_km)::numeric) AS odometer_start_km,
    ROUND(MAX(d.end_km)::numeric) AS odometer_end_km,
    ROUND(SUM(d.distance)::numeric, 1) AS distance_km,
    COUNT(*) AS drives,
    COUNT(DISTINCT ((d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date) AS days_driven
FROM drives d
    JOIN cars c ON c.id = d.car_id
WHERE d.end_date IS NOT NULL
    AND d.end_km IS NOT NULL
    AND (%(days)s::int IS NULL OR d.start_date >= CURRENT_DATE - make_interval(days => %(days)s))
    AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
GROUP BY 1, c.name
ORDER BY c.name, 1;
