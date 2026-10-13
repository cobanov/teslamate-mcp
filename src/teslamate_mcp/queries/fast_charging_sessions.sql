-- DC fast-charging sessions with the numbers that compare chargers: peak and
-- average power, average power across 20-80 percent, and the minutes from 20
-- to 80 percent when the session spanned that band.
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
SELECT d.id AS charging_process_id,
    d.car_name,
    d.start_date,
    TO_CHAR((d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text, 'YYYY-MM-DD HH24:MI')
        AS start_local,
    d.location,
    d.charger_type,
    d.connector,
    d.start_battery_level AS start_soc,
    d.end_battery_level AS end_soc,
    ROUND(d.charge_energy_added::numeric, 1) AS energy_added_kwh,
    d.duration_min,
    d.peak_kw AS peak_power_kw,
    ROUND(d.avg_kw::numeric, 1) AS avg_power_kw,
    ROUND(d.avg_kw_20_80::numeric, 1) AS avg_power_20_80_kw,
    ROUND(d.minutes_20_to_80::numeric) AS minutes_20_to_80,
    d.battery_heater AS battery_heater_on,
    ROUND(d.outside_temp_avg::numeric, 1) AS outside_temp_avg,
    d.cost
FROM dc_sessions d
ORDER BY CASE %(order_by)s::text
        WHEN 'peak_power' THEN d.peak_kw
        WHEN 'avg_power_20_80' THEN d.avg_kw_20_80
    END DESC NULLS LAST,
    d.start_date DESC
LIMIT %(limit)s::int;
