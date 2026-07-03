SELECT DATE((start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text) AS drive_day,
    COUNT(*) AS drive_count,
    SUM(distance) AS total_km,
    SUM(duration_min) AS total_minutes
FROM drives
    JOIN cars c ON drives.car_id = c.id
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
    AND (%(days)s::int IS NULL OR start_date >= CURRENT_DATE - make_interval(days => %(days)s))
GROUP BY DATE((start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)
ORDER BY DATE((start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text) DESC
LIMIT %(limit)s::int;