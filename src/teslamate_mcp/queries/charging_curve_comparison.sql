-- Charging power against battery level for several sessions, to overlay
-- their curves: one row per session and battery percent. Either the sessions
-- named in charging_process_ids, or the latest ones matching the filters.
WITH requested AS (
    SELECT ARRAY(
        SELECT x::int
        FROM unnest(string_to_array(
            regexp_replace(%(charging_process_ids)s::text, '\s', '', 'g'), ','
        )) AS x
        WHERE x ~ '^[0-9]+$'
    ) AS ids
),
-- DC and Supercharger tests as in the dc session stats block of
-- fast_charging_sessions.sql.
typed AS (
    SELECT cp.id,
        cp.car_id,
        cp.start_date,
        cp.address_id,
        cp.geofence_id,
        CASE
            WHEN ct.supercharger THEN 'supercharger'
            WHEN ct.dc THEN 'other_dc'
            ELSE 'ac'
        END AS charger_type
    FROM charging_processes cp
        CROSS JOIN LATERAL (
            SELECT COALESCE(BOOL_OR(ch.fast_charger_present
                    OR (ch.charger_phases IS NULL AND ch.charger_power > 0)), FALSE) AS dc,
                COALESCE(BOOL_OR(ch.fast_charger_present AND ch.fast_charger_brand = 'Tesla'),
                    FALSE) AS supercharger
            FROM charges ch
            WHERE ch.charging_process_id = cp.id
        ) ct
        CROSS JOIN requested r
    WHERE cp.end_date IS NOT NULL
        AND cp.charge_energy_added >= 1
        AND (%(charging_process_ids)s::text IS NULL OR cp.id = ANY (r.ids))
),
picked AS (
    SELECT t.*,
        c.name AS car_name,
        COALESCE(g.name, a.display_name) AS location
    FROM typed t
        JOIN cars c ON c.id = t.car_id
        LEFT JOIN addresses a ON a.id = t.address_id
        LEFT JOIN geofences g ON g.id = t.geofence_id
    -- Named sessions are taken as they are; the filters pick the others.
    WHERE %(charging_process_ids)s::text IS NOT NULL
        OR ((%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
            AND (%(location)s::text IS NULL
                OR a.display_name ILIKE '%%' || %(location)s || '%%'
                OR a.city ILIKE '%%' || %(location)s || '%%'
                OR g.name ILIKE '%%' || %(location)s || '%%')
            AND (%(charger_type)s::text = 'any'
                OR %(charger_type)s::text = t.charger_type
                OR (%(charger_type)s::text = 'dc' AND t.charger_type <> 'ac')))
    ORDER BY t.start_date DESC
    LIMIT %(limit)s::int
)
SELECT p.id AS charging_process_id,
    p.car_name,
    p.start_date,
    TO_CHAR((p.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text, 'YYYY-MM-DD HH24:MI')
        AS start_local,
    p.location,
    p.charger_type,
    ch.battery_level,
    ROUND(AVG(ch.charger_power)::numeric, 1) AS power_kw,
    MAX(ch.charger_power) AS max_power_kw,
    ROUND(AVG(ch.outside_temp)::numeric, 1) AS outside_temp
FROM picked p
    JOIN charges ch ON ch.charging_process_id = p.id
WHERE ch.battery_level IS NOT NULL
    AND ch.charger_power > 0
GROUP BY p.id, p.car_name, p.start_date, p.location, p.charger_type, ch.battery_level
ORDER BY p.start_date DESC, ch.battery_level;
