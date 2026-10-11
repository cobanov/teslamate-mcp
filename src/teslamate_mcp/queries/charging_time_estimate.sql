-- How long a charge from one battery level to another takes, from the time
-- the car's past sessions spent at each battery percent. Measured time, not
-- power over capacity, so the taper and AC losses are already in it.
WITH scope_cars AS (
    SELECT c.id,
        c.name
    FROM cars c
    WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
-- DC and Supercharger tests as in the dc session stats block of
-- fast_charging_sessions.sql.
typed AS (
    SELECT cp.id,
        cp.car_id,
        cp.charge_energy_added,
        cp.start_battery_level,
        cp.end_battery_level,
        CASE
            WHEN ct.supercharger THEN 'supercharger'
            WHEN ct.dc THEN 'other_dc'
            ELSE 'ac'
        END AS charger_type
    FROM charging_processes cp
        JOIN scope_cars c ON c.id = cp.car_id
        CROSS JOIN LATERAL (
            SELECT COALESCE(BOOL_OR(ch.fast_charger_present
                    OR (ch.charger_phases IS NULL AND ch.charger_power > 0)), FALSE) AS dc,
                COALESCE(BOOL_OR(ch.fast_charger_present AND ch.fast_charger_brand = 'Tesla'),
                    FALSE) AS supercharger
            FROM charges ch
            WHERE ch.charging_process_id = cp.id
        ) ct
        LEFT JOIN addresses a ON a.id = cp.address_id
        LEFT JOIN geofences g ON g.id = cp.geofence_id
    WHERE cp.end_date IS NOT NULL
        AND cp.charge_energy_added >= 1
        AND cp.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
        AND (%(location)s::text IS NULL
            OR a.display_name ILIKE '%%' || %(location)s || '%%'
            OR a.city ILIKE '%%' || %(location)s || '%%'
            OR g.name ILIKE '%%' || %(location)s || '%%')
),
picked AS (
    SELECT t.*
    FROM typed t
    WHERE %(charger_type)s::text = 'any'
        OR %(charger_type)s::text = t.charger_type
        OR (%(charger_type)s::text = 'dc' AND t.charger_type <> 'ac')
),
-- Each sample stands for the time until the next one in its session.
samples AS (
    SELECT p.id,
        p.car_id,
        p.charger_type,
        ch.battery_level,
        ch.charger_power,
        MAX(ch.battery_level) OVER (PARTITION BY p.id) AS top_level,
        EXTRACT(EPOCH FROM (
            LEAD(ch.date) OVER (PARTITION BY p.id ORDER BY ch.date) - ch.date
        )) AS dt
    FROM picked p
        JOIN charges ch ON ch.charging_process_id = p.id
    WHERE ch.battery_level IS NOT NULL
),
-- Seconds each session spent at each battery percent while power flowed.
-- Gaps over 5 minutes are logging holes. The level a session stopped at is
-- left out: the car did not charge through it.
per_session AS (
    SELECT s.id,
        s.car_id,
        s.charger_type,
        s.battery_level,
        SUM(s.dt) AS secs
    FROM samples s
    WHERE s.charger_power > 0
        AND s.dt > 0
        AND s.dt <= 300
        AND s.battery_level < s.top_level
    GROUP BY s.id, s.car_id, s.charger_type, s.battery_level
),
per_level AS (
    SELECT car_id,
        charger_type,
        battery_level,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY secs) AS secs,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY secs) AS secs_slow
    FROM per_session
    GROUP BY car_id, charger_type, battery_level
),
history AS (
    SELECT car_id,
        charger_type,
        COUNT(DISTINCT id) AS sessions,
        MIN(battery_level) AS soc_from,
        MAX(battery_level) + 1 AS soc_to
    FROM per_session
    GROUP BY car_id, charger_type
),
-- kWh added per battery percent, the median over sessions that added at
-- least 10 percent.
energy AS (
    SELECT car_id,
        charger_type,
        PERCENTILE_CONT(0.5) WITHIN GROUP (
            ORDER BY charge_energy_added / NULLIF(end_battery_level - start_battery_level, 0)
        ) FILTER (WHERE end_battery_level - start_battery_level >= 10) AS kwh_per_pct
    FROM picked
    GROUP BY car_id, charger_type
),
latest AS (
    SELECT c.id AS car_id,
        p.battery_level
    FROM scope_cars c
        LEFT JOIN LATERAL (
            SELECT p.battery_level
            FROM positions p
            WHERE p.car_id = c.id
                AND p.ideal_battery_range_km IS NOT NULL
                AND p.battery_level IS NOT NULL
            ORDER BY p.date DESC
            LIMIT 1
        ) p ON TRUE
),
estimate AS (
    SELECT c.name AS car_name,
        h.charger_type,
        COALESCE(%(start_soc)s::int, lt.battery_level) AS start_soc,
        %(target_soc)s::int AS target_soc,
        h.sessions,
        h.soc_from,
        h.soc_to,
        en.kwh_per_pct,
        lv.levels,
        lv.secs,
        lv.secs_slow
    FROM history h
        JOIN scope_cars c ON c.id = h.car_id
        LEFT JOIN latest lt ON lt.car_id = h.car_id
        LEFT JOIN energy en ON en.car_id = h.car_id AND en.charger_type = h.charger_type
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS levels,
                SUM(pl.secs) AS secs,
                SUM(pl.secs_slow) AS secs_slow
            FROM per_level pl
            WHERE pl.car_id = h.car_id
                AND pl.charger_type = h.charger_type
                AND pl.battery_level >= COALESCE(%(start_soc)s::int, lt.battery_level)
                AND pl.battery_level < %(target_soc)s::int
        ) lv ON TRUE
)
SELECT e.car_name,
    e.charger_type,
    e.start_soc,
    e.target_soc,
    -- An estimate only when every percent on the way has history behind it.
    CASE
        WHEN e.start_soc >= e.target_soc THEN 0
        WHEN e.levels = e.target_soc - e.start_soc THEN ROUND((e.secs / 60)::numeric)
    END AS minutes,
    CASE
        WHEN e.start_soc >= e.target_soc THEN 0
        WHEN e.levels = e.target_soc - e.start_soc THEN ROUND((e.secs_slow / 60)::numeric)
    END AS minutes_slow,
    ROUND((GREATEST(e.target_soc - e.start_soc, 0) * e.kwh_per_pct)::numeric, 1)
        AS energy_added_kwh,
    CASE WHEN e.levels = e.target_soc - e.start_soc THEN
        ROUND(((e.target_soc - e.start_soc) * e.kwh_per_pct * 3600 / NULLIF(e.secs, 0))::numeric, 1)
    END AS avg_power_kw,
    e.sessions AS sessions_used,
    e.soc_from AS history_soc_from,
    e.soc_to AS history_soc_to
FROM estimate e
ORDER BY e.car_name,
    CASE e.charger_type
        WHEN 'supercharger' THEN 1
        WHEN 'other_dc' THEN 2
        ELSE 3
    END;
