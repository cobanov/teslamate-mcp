-- Online periods from TeslaMate's state log, minus the time spent driving
-- and charging inside them: what is left is the car awake while parked,
-- which keeps it from sleeping and drains the battery. Longest idle first.
-- An open online state ends at the car's last logged position; see
-- state_history.sql for why it cannot simply run to now().
WITH scope AS (
    SELECT s.car_id,
        c.name AS car_name,
        s.start_date,
        COALESCE(s.end_date, GREATEST(s.start_date, seen.last_seen)) AS end_date,
        s.end_date IS NULL AS ongoing
    FROM states s
        JOIN cars c ON c.id = s.car_id
        LEFT JOIN LATERAL (
            SELECT p.date AS last_seen
            FROM positions p
            WHERE s.end_date IS NULL
                AND p.car_id = s.car_id
                AND p.ideal_battery_range_km IS NOT NULL
            ORDER BY p.date DESC
            LIMIT 1
        ) seen ON TRUE
    WHERE s.state::text = 'online'
        AND COALESCE(s.end_date, now() AT TIME ZONE 'UTC')
            >= (now() AT TIME ZONE 'UTC') - make_interval(days => %(days)s::int)
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
periods AS (
    SELECT sc.*,
        EXTRACT(EPOCH FROM (sc.end_date - sc.start_date)) AS online_s,
        COALESCE(dr.driving_s, 0) AS driving_s,
        COALESCE(dr.drives, 0) AS drives,
        COALESCE(ch.charging_s, 0) AS charging_s,
        park.end_address_id
    FROM scope sc
        -- Drives with no end_date are TeslaMate orphans; see state_history.sql.
        LEFT JOIN LATERAL (
            SELECT SUM(EXTRACT(EPOCH FROM (
                    LEAST(d.end_date, sc.end_date) - GREATEST(d.start_date, sc.start_date)
                ))) AS driving_s,
                COUNT(*) AS drives
            FROM drives d
            WHERE d.car_id = sc.car_id
                AND d.end_date IS NOT NULL
                AND d.start_date < sc.end_date
                AND d.end_date > sc.start_date
        ) dr ON TRUE
        LEFT JOIN LATERAL (
            SELECT SUM(EXTRACT(EPOCH FROM (
                    LEAST(cp.effective_end, sc.end_date) - GREATEST(cp.start_date, sc.start_date)
                ))) AS charging_s
            FROM (
                SELECT cp.start_date,
                    COALESCE(cp.end_date, (
                        SELECT MAX(chg.date)
                        FROM charges chg
                        WHERE chg.charging_process_id = cp.id
                    )) AS effective_end
                FROM charging_processes cp
                WHERE cp.car_id = sc.car_id
                    AND cp.start_date < sc.end_date
            ) cp
            WHERE cp.effective_end > sc.start_date
        ) ch ON TRUE
        -- Where the car stood: the end of its last drive before the period ended.
        LEFT JOIN LATERAL (
            SELECT d.end_address_id
            FROM drives d
            WHERE d.car_id = sc.car_id
                AND d.end_date IS NOT NULL
                AND d.end_date <= sc.end_date
            ORDER BY d.end_date DESC
            LIMIT 1
        ) park ON TRUE
)
SELECT p.car_name,
    p.start_date,
    CASE WHEN p.ongoing THEN NULL ELSE p.end_date END AS end_date,
    TO_CHAR((p.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text, 'YYYY-MM-DD HH24:MI')
        AS start_local,
    p.ongoing,
    ROUND((p.online_s / 3600.0)::numeric, 1) AS online_hours,
    ROUND((GREATEST(p.online_s - p.driving_s - p.charging_s, 0) / 3600.0)::numeric, 1)
        AS idle_awake_hours,
    p.drives AS drives_during,
    p.charging_s > 0 AS charged_during,
    a.display_name AS location,
    a.city
FROM periods p
    LEFT JOIN addresses a ON a.id = p.end_address_id
WHERE p.online_s - p.driving_s - p.charging_s >= %(min_idle_minutes)s::int * 60
ORDER BY p.online_s - p.driving_s - p.charging_s DESC
LIMIT %(limit)s::int;
