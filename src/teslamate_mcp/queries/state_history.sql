-- Per car and local day: how long the car was online, asleep, or offline,
-- how much of the online time went to driving and charging, and what was
-- left over as idle-awake time (the time that drains the battery while
-- parked). Every interval is clipped to the local day it overlaps, so a night
-- asleep counts toward both days it spans.
WITH days AS (
    SELECT c.id AS car_id,
        c.name AS car_name,
        d::date AS day,
        (d AT TIME ZONE %(tz)s::text) AT TIME ZONE 'UTC' AS day_start,
        ((d + interval '1 day') AT TIME ZONE %(tz)s::text) AT TIME ZONE 'UTC' AS day_end
    FROM cars c
        CROSS JOIN generate_series(
            ((now() AT TIME ZONE %(tz)s::text)::date - (%(days)s::int - 1))::timestamp,
            (now() AT TIME ZONE %(tz)s::text)::date::timestamp,
            interval '1 day'
        ) AS d
    WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
-- An open online state ends at the car's last logged position, not at now():
-- when TeslaMate loses contact with a car (API token revoked, car sold) the
-- state stays open and online for months. Open asleep and offline states do
-- run to now(), since a sleeping car logs no positions.
states_scoped AS (
    SELECT s.car_id,
        s.state::text AS state,
        s.start_date,
        CASE
            WHEN s.end_date IS NOT NULL THEN s.end_date
            WHEN s.state::text = 'online' THEN GREATEST(s.start_date, seen.last_seen)
            ELSE now() AT TIME ZONE 'UTC'
        END AS end_date
    FROM states s
        LEFT JOIN LATERAL (
            SELECT p.date AS last_seen
            FROM positions p
            WHERE s.end_date IS NULL
                AND p.car_id = s.car_id
                AND p.ideal_battery_range_km IS NOT NULL
            ORDER BY p.date DESC
            LIMIT 1
        ) seen ON TRUE
    WHERE s.car_id IN (SELECT DISTINCT car_id FROM days)
        AND s.start_date < (SELECT MAX(day_end) FROM days)
        AND (s.end_date IS NULL OR s.end_date > (SELECT MIN(day_start) FROM days))
),
state_time AS (
    SELECT dy.car_id,
        dy.day,
        SUM(ov.seconds) FILTER (WHERE s.state = 'online') AS online_s,
        SUM(ov.seconds) FILTER (WHERE s.state = 'asleep') AS asleep_s,
        SUM(ov.seconds) FILTER (WHERE s.state = 'offline') AS offline_s,
        COUNT(*) FILTER (
            WHERE s.state = 'online'
                AND s.start_date >= dy.day_start
                AND s.start_date < dy.day_end
        ) AS wakeups
    FROM days dy
        JOIN states_scoped s ON s.car_id = dy.car_id
            AND s.start_date < dy.day_end
            AND s.end_date > dy.day_start
        CROSS JOIN LATERAL (
            SELECT EXTRACT(EPOCH FROM (
                LEAST(s.end_date, dy.day_end) - GREATEST(s.start_date, dy.day_start)
            )) AS seconds
        ) ov
    GROUP BY dy.car_id, dy.day
),
-- Drives still missing an end_date are skipped: TeslaMate leaves orphans
-- behind when it restarts mid-drive, and they carry no distance or duration.
drive_time AS (
    SELECT dy.car_id,
        dy.day,
        SUM(EXTRACT(EPOCH FROM (
            LEAST(d.end_date, dy.day_end) - GREATEST(d.start_date, dy.day_start)
        ))) AS driving_s
    FROM days dy
        JOIN drives d ON d.car_id = dy.car_id
            AND d.end_date IS NOT NULL
            AND d.start_date < dy.day_end
            AND d.end_date > dy.day_start
    GROUP BY dy.car_id, dy.day
),
-- A session still in progress (no end_date yet) runs up to its latest sample.
charge_time AS (
    SELECT dy.car_id,
        dy.day,
        SUM(EXTRACT(EPOCH FROM (
            LEAST(cp.effective_end, dy.day_end) - GREATEST(cp.start_date, dy.day_start)
        ))) AS charging_s
    FROM days dy
        JOIN (
            SELECT cp.car_id,
                cp.start_date,
                COALESCE(cp.end_date, (
                    SELECT MAX(ch.date) FROM charges ch WHERE ch.charging_process_id = cp.id
                )) AS effective_end
            FROM charging_processes cp
        ) cp ON cp.car_id = dy.car_id
            AND cp.start_date < dy.day_end
            AND cp.effective_end > dy.day_start
    GROUP BY dy.car_id, dy.day
)
SELECT dy.car_name,
    dy.day,
    ROUND((COALESCE(st.online_s, 0) / 3600.0)::numeric, 1) AS online_hours,
    ROUND((COALESCE(st.asleep_s, 0) / 3600.0)::numeric, 1) AS asleep_hours,
    ROUND((COALESCE(st.offline_s, 0) / 3600.0)::numeric, 1) AS offline_hours,
    ROUND((COALESCE(dt.driving_s, 0) / 3600.0)::numeric, 1) AS driving_hours,
    ROUND((COALESCE(ct.charging_s, 0) / 3600.0)::numeric, 1) AS charging_hours,
    ROUND((GREATEST(
        COALESCE(st.online_s, 0) - COALESCE(dt.driving_s, 0) - COALESCE(ct.charging_s, 0), 0
    ) / 3600.0)::numeric, 1) AS idle_awake_hours,
    COALESCE(st.wakeups, 0) AS wakeups,
    ROUND((100 * (COALESCE(st.asleep_s, 0) + COALESCE(st.offline_s, 0))
        / NULLIF(COALESCE(st.online_s, 0) + COALESCE(st.asleep_s, 0) + COALESCE(st.offline_s, 0), 0)
    )::numeric, 1) AS pct_asleep_or_offline
FROM days dy
    JOIN state_time st ON st.car_id = dy.car_id AND st.day = dy.day
    LEFT JOIN drive_time dt ON dt.car_id = dy.car_id AND dt.day = dy.day
    LEFT JOIN charge_time ct ON ct.car_id = dy.car_id AND ct.day = dy.day
ORDER BY dy.car_name, dy.day DESC;
