WITH drive_stats AS (
    SELECT
        COALESCE(SUM(d.distance) FILTER (WHERE d.start_date >= now()
            - make_interval(days => %(days)s::int)), 0) AS cur_distance,
        COALESCE(SUM(d.distance) FILTER (WHERE d.start_date < now()
            - make_interval(days => %(days)s)), 0) AS prev_distance,
        COUNT(*) FILTER (WHERE d.start_date >= now()
            - make_interval(days => %(days)s)) AS cur_drives,
        COUNT(*) FILTER (WHERE d.start_date < now()
            - make_interval(days => %(days)s)) AS prev_drives
    FROM drives d
        JOIN cars c ON d.car_id = c.id
    WHERE d.start_date >= now() - make_interval(days => 2 * %(days)s)
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
charge_stats AS (
    SELECT
        COALESCE(SUM(cp.charge_energy_added) FILTER (WHERE cp.start_date >= now()
            - make_interval(days => %(days)s)), 0) AS cur_kwh,
        COALESCE(SUM(cp.charge_energy_added) FILTER (WHERE cp.start_date < now()
            - make_interval(days => %(days)s)), 0) AS prev_kwh,
        COALESCE(SUM(cp.cost) FILTER (WHERE cp.start_date >= now()
            - make_interval(days => %(days)s)), 0) AS cur_cost,
        COALESCE(SUM(cp.cost) FILTER (WHERE cp.start_date < now()
            - make_interval(days => %(days)s)), 0) AS prev_cost,
        COUNT(*) FILTER (WHERE cp.start_date >= now()
            - make_interval(days => %(days)s)) AS cur_sessions,
        COUNT(*) FILTER (WHERE cp.start_date < now()
            - make_interval(days => %(days)s)) AS prev_sessions
    FROM charging_processes cp
        JOIN cars c ON cp.car_id = c.id
    WHERE cp.start_date >= now() - make_interval(days => 2 * %(days)s)
        AND (%(car_name)s IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
)
SELECT 'distance_km' AS metric,
    ROUND(ds.cur_distance::numeric, 1) AS current_value,
    ROUND(ds.prev_distance::numeric, 1) AS previous_value,
    ROUND(100 * (ds.cur_distance - ds.prev_distance)::numeric
        / NULLIF(ds.prev_distance::numeric, 0), 1) AS change_pct
FROM drive_stats ds
UNION ALL
SELECT 'drive_count',
    ds.cur_drives::numeric,
    ds.prev_drives::numeric,
    ROUND(100 * (ds.cur_drives - ds.prev_drives)::numeric / NULLIF(ds.prev_drives::numeric, 0), 1)
FROM drive_stats ds
UNION ALL
SELECT 'kwh_added',
    ROUND(cs.cur_kwh::numeric, 1),
    ROUND(cs.prev_kwh::numeric, 1),
    ROUND(100 * (cs.cur_kwh - cs.prev_kwh)::numeric / NULLIF(cs.prev_kwh::numeric, 0), 1)
FROM charge_stats cs
UNION ALL
SELECT 'charge_cost',
    ROUND(cs.cur_cost::numeric, 2),
    ROUND(cs.prev_cost::numeric, 2),
    ROUND(100 * (cs.cur_cost - cs.prev_cost)::numeric / NULLIF(cs.prev_cost::numeric, 0), 1)
FROM charge_stats cs
UNION ALL
SELECT 'charge_sessions',
    cs.cur_sessions::numeric,
    cs.prev_sessions::numeric,
    ROUND(100 * (cs.cur_sessions - cs.prev_sessions)::numeric
        / NULLIF(cs.prev_sessions::numeric, 0), 1)
FROM charge_stats cs;
