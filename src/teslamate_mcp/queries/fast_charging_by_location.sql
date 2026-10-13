-- DC fast-charging per location and charger type: how often, how fast
-- (average and best peak power, average power across 20-80 percent, minutes
-- from 20 to 80 percent), how much energy, and the price paid per kWh.
WITH
-- dc session stats: begin (keep identical in fast_charging_sessions.sql and
-- fast_charging_by_location.sql)
sessions AS (
    SELECT cp.id,
        cp.car_id,
        c.name AS car_name,
        cp.start_date,
        cp.duration_min,
        cp.charge_energy_added,
        cp.start_battery_level,
        cp.end_battery_level,
        cp.outside_temp_avg,
        cp.cost,
        cp.address_id,
        cp.geofence_id
    FROM charging_processes cp
        JOIN cars c ON c.id = cp.car_id
    WHERE cp.end_date IS NOT NULL
        AND cp.charge_energy_added >= 1
        AND cp.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
-- DC: a sample came from a fast charger, or had no AC phases while power
-- flowed. AC sessions often end on a 0 kW sample with no phases, which must
-- not count. A Tesla-branded fast charger is a Supercharger.
stats AS (
    SELECT s.id,
        BOOL_OR(ch.fast_charger_present OR (ch.charger_phases IS NULL AND ch.charger_power > 0))
            AS dc,
        BOOL_OR(ch.fast_charger_present AND ch.fast_charger_brand = 'Tesla') AS supercharger,
        MODE() WITHIN GROUP (ORDER BY ch.fast_charger_type)
            FILTER (WHERE ch.fast_charger_type <> '<invalid>') AS connector,
        MAX(ch.charger_power) AS peak_kw,
        AVG(ch.charger_power) FILTER (
            WHERE ch.battery_level BETWEEN 20 AND 80
                AND ch.charger_power > 0
        ) AS avg_kw_20_80,
        CASE WHEN MIN(ch.battery_level) <= 20 AND MAX(ch.battery_level) >= 80 THEN
            EXTRACT(EPOCH FROM (
                MIN(ch.date) FILTER (WHERE ch.battery_level >= 80)
                    - MIN(ch.date) FILTER (WHERE ch.battery_level >= 20)
            )) / 60.0
        END AS minutes_20_to_80,
        COALESCE(BOOL_OR(ch.battery_heater_on), FALSE) AS battery_heater
    FROM sessions s
        JOIN charges ch ON ch.charging_process_id = s.id
    GROUP BY s.id
),
dc_sessions AS (
    SELECT s.*,
        st.peak_kw,
        s.charge_energy_added * 60 / NULLIF(s.duration_min, 0) AS avg_kw,
        st.avg_kw_20_80,
        st.minutes_20_to_80,
        st.connector,
        st.battery_heater,
        CASE WHEN st.supercharger THEN 'supercharger' ELSE 'other_dc' END AS charger_type,
        COALESCE(g.name, a.display_name) AS location,
        a.city
    FROM sessions s
        JOIN stats st ON st.id = s.id AND st.dc
        LEFT JOIN addresses a ON a.id = s.address_id
        LEFT JOIN geofences g ON g.id = s.geofence_id
    WHERE (%(location)s::text IS NULL
            OR a.display_name ILIKE '%%' || %(location)s || '%%'
            OR a.city ILIKE '%%' || %(location)s || '%%'
            OR g.name ILIKE '%%' || %(location)s || '%%')
        AND (%(charger_type)s::text = 'dc'
            OR %(charger_type)s::text
                = CASE WHEN st.supercharger THEN 'supercharger' ELSE 'other_dc' END)
)
-- dc session stats: end
SELECT d.location,
    d.city,
    d.charger_type,
    COUNT(*) AS sessions,
    ROUND(AVG(d.peak_kw)::numeric) AS avg_peak_power_kw,
    MAX(d.peak_kw) AS best_peak_power_kw,
    ROUND(AVG(d.avg_kw)::numeric, 1) AS avg_power_kw,
    ROUND(AVG(d.avg_kw_20_80)::numeric, 1) AS avg_power_20_80_kw,
    ROUND(AVG(d.minutes_20_to_80)::numeric) AS avg_minutes_20_to_80,
    ROUND(SUM(d.charge_energy_added)::numeric, 1) AS energy_added_kwh,
    ROUND((SUM(d.cost)
        / NULLIF(SUM(d.charge_energy_added) FILTER (WHERE d.cost IS NOT NULL), 0))::numeric, 3)
        AS avg_cost_per_kwh,
    COUNT(*) FILTER (WHERE d.battery_heater) AS sessions_with_battery_heating,
    MAX(d.start_date) AS last_visit
FROM dc_sessions d
GROUP BY d.location, d.city, d.charger_type
HAVING COUNT(*) >= %(min_sessions)s::int
ORDER BY CASE %(order_by)s::text
        WHEN 'avg_power_20_80' THEN AVG(d.avg_kw_20_80)
        WHEN 'peak_power' THEN AVG(d.peak_kw)
        ELSE COUNT(*)
    END DESC NULLS LAST,
    MAX(d.start_date) DESC
LIMIT %(limit)s::int;
