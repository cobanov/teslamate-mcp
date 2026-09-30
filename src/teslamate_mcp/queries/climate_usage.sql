-- Monthly totals of the climate running while parked; the sessions are built
-- exactly as in parked_climate_sessions.sql (see there). Months are local
-- (REPORT_TIMEZONE); a session counts in the month it started. The cost is
-- the energy at that month's average recorded price per billed kWh.
WITH window_start AS (
    -- The first local day of the month `months - 1` months back, in UTC.
    SELECT (date_trunc('month', now() AT TIME ZONE %(tz)s::text)
            - make_interval(months => %(months)s::int - 1))
            AT TIME ZONE %(tz)s::text AT TIME ZONE 'UTC' AS since_utc
),
scope_cars AS (
    SELECT c.id,
        c.name
    FROM cars c
    WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
parks AS (
    SELECT d.car_id,
        d.end_date AS park_start,
        LEAD(d.start_date) OVER (PARTITION BY d.car_id ORDER BY d.start_date) AS park_end,
        d.end_address_id,
        d.end_geofence_id
    FROM drives d
    WHERE d.car_id IN (SELECT id FROM scope_cars)
        AND d.end_date IS NOT NULL
),
samples AS (
    SELECT p.car_id,
        p.date,
        p.is_climate_on,
        p.power,
        p.inside_temp,
        p.outside_temp,
        p.driver_temp_setting,
        pk.park_start,
        pk.park_end,
        pk.end_address_id,
        pk.end_geofence_id,
        LEAD(p.date) OVER w AS next_date,
        LAG(p.date) OVER w AS prev_date,
        LAG(p.is_climate_on) OVER w AS prev_on
    FROM positions p
        JOIN parks pk ON pk.car_id = p.car_id
            AND p.date >= pk.park_start
            AND p.date < COALESCE(pk.park_end, 'infinity')
    WHERE p.drive_id IS NULL
        AND p.is_climate_on IS NOT NULL
        AND p.date >= (SELECT since_utc FROM window_start)
    WINDOW w AS (PARTITION BY p.car_id, pk.park_start ORDER BY p.date)
),
marked AS (
    SELECT s.*,
        LEAST(s.date + interval '10 minutes', COALESCE(s.next_date, 'infinity'),
            COALESCE(s.park_end, 'infinity')) AS credit_end,
        EXISTS (
            SELECT 1
            FROM charging_processes cp
            WHERE cp.car_id = s.car_id
                AND s.date >= cp.start_date
                AND s.date <= COALESCE(cp.end_date, 'infinity')
        ) AS plugged_in,
        CASE WHEN s.prev_on IS DISTINCT FROM s.is_climate_on
                OR s.date - s.prev_date > interval '15 minutes' THEN 1 ELSE 0 END AS new_group
    FROM samples s
),
grouped AS (
    SELECT m.*,
        SUM(m.new_group) OVER (PARTITION BY m.car_id, m.park_start ORDER BY m.date) AS grp
    FROM marked m
),
sessions AS (
    SELECT g.car_id,
        g.park_start,
        MIN(g.park_end) AS park_end,
        MIN(g.end_address_id) AS address_id,
        MIN(g.end_geofence_id) AS geofence_id,
        MIN(g.date) AS start_date,
        MAX(g.credit_end) AS end_date,
        COALESCE(SUM(GREATEST(g.power, 0) * EXTRACT(EPOCH FROM (g.credit_end - g.date)) / 3600.0)
            FILTER (WHERE NOT g.plugged_in), 0) AS kwh,
        BOOL_OR(g.plugged_in) AS plugged_in,
        AVG(g.outside_temp) AS outside_temp,
        AVG(g.inside_temp) AS inside_temp,
        AVG(g.driver_temp_setting) AS setpoint
    FROM grouped g
    WHERE g.is_climate_on
    GROUP BY g.car_id, g.park_start, g.grp
),
monthly AS (
    SELECT s.car_id,
        date_trunc('month', (s.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date
            AS month,
        COUNT(*) AS sessions,
        COUNT(*) FILTER (WHERE s.park_end - s.end_date <= interval '5 minutes') AS before_drive,
        SUM(EXTRACT(EPOCH FROM (s.end_date - s.start_date))) / 3600.0 AS hours,
        SUM(EXTRACT(EPOCH FROM (s.end_date - s.start_date))) FILTER (WHERE s.plugged_in)
            / 3600.0 AS plugged_hours,
        SUM(s.kwh) AS kwh,
        SUM(s.outside_temp * EXTRACT(EPOCH FROM (s.end_date - s.start_date)))
            / NULLIF(SUM(EXTRACT(EPOCH FROM (s.end_date - s.start_date)))
                FILTER (WHERE s.outside_temp IS NOT NULL), 0) AS outside_temp,
        COUNT(*) FILTER (WHERE s.outside_temp > s.setpoint) AS cooling
    FROM sessions s
    WHERE s.end_date - s.start_date >= make_interval(mins => %(min_minutes)s::int)
    GROUP BY 1, 2
),
prices AS (
    SELECT cp.car_id,
        date_trunc('month', (cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date
            AS month,
        SUM(cp.cost) / NULLIF(SUM(GREATEST(cp.charge_energy_used, cp.charge_energy_added)), 0)
            AS per_kwh
    FROM charging_processes cp
    WHERE cp.car_id IN (SELECT id FROM scope_cars)
        AND cp.cost IS NOT NULL
        AND cp.start_date >= (SELECT since_utc FROM window_start)
    GROUP BY 1, 2
)
SELECT TO_CHAR(m.month, 'YYYY-MM') AS month,
    c.name AS car_name,
    m.sessions,
    m.before_drive AS before_drive_sessions,
    m.cooling AS cooling_sessions,
    ROUND(m.hours::numeric, 1) AS hours,
    ROUND(COALESCE(m.plugged_hours, 0)::numeric, 1) AS plugged_in_hours,
    ROUND(m.kwh::numeric, 1) AS energy_kwh,
    ROUND((m.kwh * p.per_kwh)::numeric, 2) AS estimated_cost,
    ROUND(m.outside_temp::numeric, 1) AS avg_outside_temp
FROM monthly m
    JOIN scope_cars c ON c.id = m.car_id
    LEFT JOIN prices p ON p.car_id = m.car_id AND p.month = m.month
ORDER BY m.month DESC, c.name;
