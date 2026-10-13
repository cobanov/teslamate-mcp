-- Everything a car did, in order: drives, charging sessions, the time parked
-- between them, and software updates. Parks are the gaps between consecutive
-- activities, so they never overlap a drive or a charge.
WITH win AS (
    SELECT (first_day::timestamp AT TIME ZONE %(tz)s::text) AT TIME ZONE 'UTC' AS win_start,
        ((last_day + 1)::timestamp AT TIME ZONE %(tz)s::text) AT TIME ZONE 'UTC' AS win_end
    FROM (
        SELECT COALESCE(%(start_date)s::date, b.last_day - 6) AS first_day,
            b.last_day
        FROM (
            SELECT COALESCE(%(end_date)s::date, (now() AT TIME ZONE %(tz)s::text)::date)
                AS last_day
        ) b
    ) d
),
scope_cars AS (
    SELECT c.id,
        c.name
    FROM cars c
    WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
-- Drives TeslaMate left open after a restart are orphans and are skipped. A
-- charging session without an end_date is included only while it is still
-- logging samples.
activities AS (
    SELECT 'drive'::text AS activity,
        d.car_id,
        d.id,
        d.start_date,
        d.end_date
    FROM drives d
    WHERE d.end_date IS NOT NULL
        AND d.car_id IN (SELECT id FROM scope_cars)
    UNION ALL
    SELECT 'charge',
        cp.car_id,
        cp.id,
        cp.start_date,
        cp.end_date
    FROM charging_processes cp
    WHERE cp.car_id IN (SELECT id FROM scope_cars)
        AND (cp.end_date IS NOT NULL OR EXISTS (
            SELECT 1
            FROM charges ch
            WHERE ch.charging_process_id = cp.id
                AND ch.date >= (now() AT TIME ZONE 'UTC') - interval '1 hour'
        ))
),
-- Sequenced over the car's whole history, so the park after the last
-- activity in the window still ends where the next activity starts.
sequenced AS (
    SELECT a.*,
        LEAD(a.activity) OVER w AS next_activity,
        LEAD(a.id) OVER w AS next_id,
        LEAD(a.start_date) OVER w AS next_start
    FROM activities a
    WINDOW w AS (PARTITION BY a.car_id ORDER BY a.start_date)
),
events AS (
    SELECT s.activity,
        s.car_id,
        s.id,
        s.start_date,
        s.end_date,
        NULL::text AS prev_activity,
        NULL::int AS prev_id,
        NULL::text AS next_activity,
        NULL::int AS next_id
    FROM sequenced s
    UNION ALL
    SELECT 'park',
        s.car_id,
        NULL,
        s.end_date,
        s.next_start,
        s.activity,
        s.id,
        s.next_activity,
        s.next_id
    FROM sequenced s
    WHERE s.end_date IS NOT NULL
        AND COALESCE(s.next_start, now() AT TIME ZONE 'UTC') - s.end_date
            >= make_interval(mins => %(min_park_minutes)s::int)
    UNION ALL
    SELECT 'update',
        u.car_id,
        u.id,
        u.start_date,
        u.end_date,
        NULL,
        NULL,
        NULL,
        NULL
    FROM updates u
    WHERE u.car_id IN (SELECT id FROM scope_cars)
),
-- The newest rows win when the window holds more than the limit.
windowed AS (
    SELECT e.*
    FROM events e
        CROSS JOIN win
    WHERE e.start_date < win.win_end
        AND COALESCE(e.end_date, now() AT TIME ZONE 'UTC') > win.win_start
    ORDER BY e.start_date DESC
    LIMIT %(limit)s::int
),
-- Places and battery levels, looked up only for the drives and charges the
-- output needs: its own rows, and the activities on either side of a park.
needed AS (
    SELECT activity, id FROM windowed WHERE activity IN ('drive', 'charge')
    UNION
    SELECT prev_activity, prev_id FROM windowed WHERE activity = 'park'
    UNION
    SELECT next_activity, next_id FROM windowed WHERE activity = 'park' AND next_id IS NOT NULL
),
endpoints AS (
    SELECT 'drive'::text AS activity,
        d.id,
        COALESCE(sg.name, sa.display_name) AS start_location,
        COALESCE(eg.name, ea.display_name) AS end_location,
        sp.battery_level AS battery_start,
        ep.battery_level AS battery_end,
        d.distance AS distance_km,
        NULL::numeric AS energy_added_kwh,
        NULL::numeric AS cost
    FROM needed n
        JOIN drives d ON n.activity = 'drive' AND d.id = n.id
        LEFT JOIN addresses sa ON sa.id = d.start_address_id
        LEFT JOIN addresses ea ON ea.id = d.end_address_id
        LEFT JOIN geofences sg ON sg.id = d.start_geofence_id
        LEFT JOIN geofences eg ON eg.id = d.end_geofence_id
        LEFT JOIN positions sp ON sp.id = d.start_position_id
        LEFT JOIN positions ep ON ep.id = d.end_position_id
    UNION ALL
    SELECT 'charge',
        cp.id,
        COALESCE(g.name, a.display_name),
        COALESCE(g.name, a.display_name),
        cp.start_battery_level,
        cp.end_battery_level,
        NULL,
        cp.charge_energy_added,
        cp.cost
    FROM needed n
        JOIN charging_processes cp ON n.activity = 'charge' AND cp.id = n.id
        LEFT JOIN addresses a ON a.id = cp.address_id
        LEFT JOIN geofences g ON g.id = cp.geofence_id
)
SELECT c.name AS car_name,
    w.activity,
    w.start_date,
    w.end_date,
    TO_CHAR((w.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text, 'YYYY-MM-DD HH24:MI')
        AS start_local,
    TO_CHAR((w.end_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text, 'YYYY-MM-DD HH24:MI')
        AS end_local,
    ROUND((EXTRACT(EPOCH FROM (
        COALESCE(w.end_date, now() AT TIME ZONE 'UTC') - w.start_date
    )) / 60.0)::numeric) AS duration_min,
    CASE WHEN w.activity = 'park' THEN prev.end_location ELSE cur.start_location END AS location,
    CASE WHEN w.activity = 'drive' THEN cur.end_location END AS destination,
    ROUND(cur.distance_km::numeric, 1) AS distance_km,
    CASE WHEN w.activity = 'park' THEN prev.battery_end ELSE cur.battery_start END
        AS battery_start,
    CASE WHEN w.activity = 'park' THEN nxt.battery_start ELSE cur.battery_end END
        AS battery_end,
    ROUND(cur.energy_added_kwh::numeric, 2) AS energy_added_kwh,
    cur.cost,
    sleep.pct AS pct_asleep_or_offline,
    CASE WHEN w.activity = 'drive' THEN w.id END AS drive_id,
    CASE WHEN w.activity = 'charge' THEN w.id END AS charging_process_id,
    u.version
FROM windowed w
    JOIN scope_cars c ON c.id = w.car_id
    LEFT JOIN endpoints cur ON cur.activity = w.activity AND cur.id = w.id
    LEFT JOIN endpoints prev ON w.activity = 'park'
        AND prev.activity = w.prev_activity
        AND prev.id = w.prev_id
    LEFT JOIN endpoints nxt ON w.activity = 'park'
        AND nxt.activity = w.next_activity
        AND nxt.id = w.next_id
    LEFT JOIN updates u ON w.activity = 'update' AND u.id = w.id
    -- Share of a park the car spent asleep or offline, from the state log
    -- (null when the log has nothing for that time).
    LEFT JOIN LATERAL (
        SELECT CASE WHEN COUNT(*) > 0 THEN ROUND((100 * COALESCE(SUM(EXTRACT(EPOCH FROM (
                    LEAST(COALESCE(s.end_date, now() AT TIME ZONE 'UTC'),
                        COALESCE(w.end_date, now() AT TIME ZONE 'UTC'))
                    - GREATEST(s.start_date, w.start_date)
                ))) FILTER (WHERE s.state::text IN ('asleep', 'offline')), 0)
            / NULLIF(EXTRACT(EPOCH FROM (
                COALESCE(w.end_date, now() AT TIME ZONE 'UTC') - w.start_date
            )), 0))::numeric) END AS pct
        FROM states s
        WHERE w.activity = 'park'
            AND s.car_id = w.car_id
            AND s.start_date < COALESCE(w.end_date, now() AT TIME ZONE 'UTC')
            AND COALESCE(s.end_date, now() AT TIME ZONE 'UTC') > w.start_date
    ) sleep ON TRUE
ORDER BY w.start_date, c.name;
