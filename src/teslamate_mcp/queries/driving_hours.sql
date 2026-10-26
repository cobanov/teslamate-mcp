-- When the car is driven: drives by the local weekday and hour they started.
-- A drive counts once, in the hour it started, with all its distance.
SELECT c.name AS car_name,
    EXTRACT(ISODOW FROM l.local_start)::int AS weekday,
    TRIM(TO_CHAR(l.local_start, 'Day')) AS weekday_name,
    EXTRACT(HOUR FROM l.local_start)::int AS start_hour,
    COUNT(*) AS drives,
    ROUND(SUM(d.distance)::numeric, 1) AS distance_km,
    ROUND((SUM(d.duration_min) / 60.0)::numeric, 2) AS driving_hours,
    ROUND(AVG(d.outside_temp_avg)::numeric, 1) AS avg_outside_temp
FROM drives d
    JOIN cars c ON c.id = d.car_id
    CROSS JOIN LATERAL (
        SELECT (d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text AS local_start
    ) l
WHERE d.end_date IS NOT NULL
    AND d.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
    AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
GROUP BY c.name, 2, 3, 4
ORDER BY c.name, 2, 4;
