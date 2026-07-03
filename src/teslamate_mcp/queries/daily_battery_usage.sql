SELECT c.name as car_name,
    DATE((p.date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text) as date,
    MIN(p.battery_level) as min_battery,
    MAX(p.battery_level) as max_battery,
    MAX(p.battery_level) - MIN(p.battery_level) as daily_usage
FROM positions p
    JOIN cars c ON p.car_id = c.id
WHERE p.date >= CURRENT_DATE - make_interval(days => %(days)s::int)
    AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
GROUP BY c.id,
    c.name,
    DATE((p.date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)
HAVING MAX(p.battery_level) - MIN(p.battery_level) > %(min_swing_pct)s::int -- Filter out days with minimal usage
ORDER BY car_name,
    date DESC;