-- One charging session, AC or DC. Fast-charge tools list DC only.
-- Charger kind uses the same DC test as fast_charging_sessions.sql: a sample
-- from a fast charger, or no AC phases while power flowed. A trailing 0 kW
-- sample with no phases does not make an AC session look like DC.
SELECT cp.id AS charging_process_id,
    c.name AS car_name,
    cp.start_date,
    cp.end_date,
    TO_CHAR(
        (cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text,
        'YYYY-MM-DD HH24:MI'
    ) AS start_local,
    cp.duration_min,
    cp.start_battery_level AS start_soc,
    cp.end_battery_level AS end_soc,
    ROUND(cp.charge_energy_added::numeric, 2) AS energy_added_kwh,
    ROUND(cp.charge_energy_used::numeric, 2) AS energy_used_kwh,
    cp.cost,
    g.name AS geofence_name,
    a.display_name AS location,
    CASE
        WHEN s.supercharger THEN 'supercharger'
        WHEN s.dc THEN 'other_dc'
        WHEN s.peak_power_kw IS NOT NULL THEN 'ac'
    END AS charger_kind,
    s.phases,
    s.cable,
    s.peak_power_kw
FROM charging_processes cp
    JOIN cars c ON c.id = cp.car_id
    LEFT JOIN geofences g ON g.id = cp.geofence_id
    LEFT JOIN addresses a ON a.id = cp.address_id
    LEFT JOIN LATERAL (
        SELECT BOOL_OR(
                ch.fast_charger_present
                    OR (ch.charger_phases IS NULL AND ch.charger_power > 0)
            ) AS dc,
            BOOL_OR(ch.fast_charger_present AND ch.fast_charger_brand = 'Tesla') AS supercharger,
            MODE() WITHIN GROUP (ORDER BY ch.charger_phases) FILTER (
                WHERE ch.charger_power > 0 AND ch.charger_phases IS NOT NULL
            ) AS phases,
            MODE() WITHIN GROUP (ORDER BY ch.conn_charge_cable) FILTER (
                WHERE ch.conn_charge_cable IS NOT NULL AND ch.conn_charge_cable <> ''
            ) AS cable,
            MAX(ch.charger_power) AS peak_power_kw
        FROM charges ch
        WHERE ch.charging_process_id = cp.id
    ) s ON true
WHERE cp.id = %(charging_process_id)s::int;
