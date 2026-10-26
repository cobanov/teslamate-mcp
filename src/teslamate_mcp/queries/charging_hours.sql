-- When the car charges: sessions by the local hour they started, AC and DC
-- apart (DC when a charge sample came from a fast charger, as in
-- get_charging_efficiency). Hours with no session are left out.
WITH sessions AS (
    SELECT cp.car_id,
        EXTRACT(HOUR FROM (cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::int AS hour,
        cp.charge_energy_added AS kwh,
        cp.duration_min,
        cp.start_battery_level,
        EXISTS (
            SELECT 1
            FROM charges ch
            WHERE ch.charging_process_id = cp.id
                AND (ch.fast_charger_present OR (ch.charger_phases IS NULL AND ch.charger_power > 0))
        ) AS is_dc
    FROM charging_processes cp
        JOIN cars c ON c.id = cp.car_id
    WHERE cp.end_date IS NOT NULL
        AND cp.charge_energy_added > 0
        AND cp.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
)
SELECT c.name AS car_name,
    s.hour AS start_hour,
    COUNT(*) AS sessions,
    COUNT(*) FILTER (WHERE NOT s.is_dc) AS ac_sessions,
    COUNT(*) FILTER (WHERE s.is_dc) AS dc_sessions,
    ROUND(SUM(s.kwh)::numeric, 1) AS energy_added_kwh,
    ROUND((100 * SUM(s.kwh) / SUM(SUM(s.kwh)) OVER (PARTITION BY s.car_id))::numeric, 1)
        AS share_of_energy_pct,
    ROUND(AVG(s.duration_min)::numeric) AS avg_duration_min,
    ROUND(AVG(s.start_battery_level)::numeric) AS avg_start_level
FROM sessions s
    JOIN cars c ON c.id = s.car_id
GROUP BY s.car_id, c.name, s.hour
ORDER BY c.name, s.hour;
