-- Estimated costs for charging sessions that have none recorded. Billed
-- energy is the larger of kWh drawn and kWh added, as TeslaMate uses for
-- geofence tariffs. Each session takes the first basis that applies:
--   1. free Supercharging (car setting) on a Tesla Supercharger: 0
--   2. the price_per_kwh argument (plus session_fee)
--   3. the session's geofence tariff (per kWh or per minute, plus its fee)
--   4. the median price per kWh of the 5 costed sessions nearest in time at
--      the same address
--   5. the median price per kWh of the 10 costed sessions nearest in time
--      with the same charger type (Supercharger, other DC, AC)
WITH sessions AS (
    SELECT cp.id,
        cp.car_id,
        cp.start_date,
        cp.cost,
        cp.duration_min,
        cp.charge_energy_added,
        GREATEST(cp.charge_energy_used, cp.charge_energy_added) AS billed_kwh,
        cp.address_id,
        cp.geofence_id,
        -- DC: a sample from a fast charger, or with no AC phases while power
        -- flowed. AC sessions often end on a 0 kW sample with no phases.
        CASE
            WHEN ct.supercharger THEN 'supercharger'
            WHEN ct.dc THEN 'other_dc'
            ELSE 'ac'
        END AS charger_type
    FROM charging_processes cp
        CROSS JOIN LATERAL (
            SELECT COALESCE(BOOL_OR(ch.fast_charger_present AND ch.fast_charger_brand = 'Tesla'), FALSE)
                    AS supercharger,
                COALESCE(BOOL_OR(ch.fast_charger_present
                    OR (ch.charger_phases IS NULL AND ch.charger_power > 0)), FALSE) AS dc
            FROM charges ch
            WHERE ch.charging_process_id = cp.id
        ) ct
    WHERE cp.end_date IS NOT NULL
),
priced AS (
    SELECT s.address_id,
        s.charger_type,
        s.start_date,
        s.cost,
        s.cost / s.billed_kwh AS unit_price
    FROM sessions s
    WHERE s.cost IS NOT NULL
        AND s.billed_kwh > 0
),
targets AS (
    SELECT s.*,
        c.name AS car_name,
        cs.free_supercharging,
        COALESCE(g.name, a.display_name) AS location,
        g.name AS geofence_name,
        g.billing_type::text AS billing_type,
        g.cost_per_unit,
        g.session_fee AS geofence_fee
    FROM sessions s
        JOIN cars c ON c.id = s.car_id
        LEFT JOIN car_settings cs ON cs.id = c.settings_id
        LEFT JOIN addresses a ON a.id = s.address_id
        LEFT JOIN geofences g ON g.id = s.geofence_id
    WHERE s.cost IS NULL
        -- Aborted plug-ins that added nothing have nothing to estimate.
        AND s.billed_kwh >= 0.1
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
        AND (%(start_date)s::date IS NULL
            OR ((s.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date
                >= %(start_date)s::date)
        AND (%(end_date)s::date IS NULL
            OR ((s.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date
                <= %(end_date)s::date)
        AND (%(location)s::text IS NULL
            OR a.display_name ILIKE '%%' || %(location)s || '%%'
            OR a.city ILIKE '%%' || %(location)s || '%%'
            OR g.name ILIKE '%%' || %(location)s || '%%')
        AND (%(charger_type)s::text = 'any'
            OR %(charger_type)s::text = s.charger_type
            OR (%(charger_type)s::text = 'dc' AND s.charger_type <> 'ac'))
    ORDER BY s.start_date DESC
    LIMIT %(limit)s::int
),
estimated AS (
    SELECT t.*,
        loc.price AS place_price,
        loc.n AS place_sessions,
        typ.price AS type_price,
        typ.n AS type_sessions
    FROM targets t
        LEFT JOIN LATERAL (
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY near.unit_price) AS price,
                COUNT(*) AS n
            FROM (
                SELECT p.unit_price
                FROM priced p
                WHERE p.address_id = t.address_id
                ORDER BY ABS(EXTRACT(EPOCH FROM (p.start_date - t.start_date)))
                LIMIT 5
            ) near
        ) loc ON TRUE
        -- Free sessions say nothing about what a charger type costs elsewhere.
        LEFT JOIN LATERAL (
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY near.unit_price) AS price,
                COUNT(*) AS n
            FROM (
                SELECT p.unit_price
                FROM priced p
                WHERE p.charger_type = t.charger_type
                    AND p.cost > 0
                ORDER BY ABS(EXTRACT(EPOCH FROM (p.start_date - t.start_date)))
                LIMIT 10
            ) near
        ) typ ON TRUE
),
decided AS (
    SELECT e.*,
        CASE
            WHEN e.charger_type = 'supercharger' AND e.free_supercharging THEN 'free'
            WHEN %(price_per_kwh)s::float8 IS NOT NULL THEN 'argument'
            WHEN e.billing_type = 'per_kwh' AND e.cost_per_unit IS NOT NULL THEN 'geofence_kwh'
            WHEN e.billing_type = 'per_minute' AND e.cost_per_unit IS NOT NULL
                THEN 'geofence_minute'
            WHEN e.place_sessions > 0 THEN 'place'
            WHEN e.type_sessions > 0 THEN 'type'
        END AS basis_kind
    FROM estimated e
)
SELECT d.id AS charging_process_id,
    d.car_name,
    d.start_date,
    TO_CHAR((d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text, 'YYYY-MM-DD HH24:MI')
        AS start_local,
    d.location,
    d.charger_type,
    ROUND(d.charge_energy_added::numeric, 2) AS energy_added_kwh,
    ROUND(d.billed_kwh::numeric, 2) AS energy_billed_kwh,
    d.duration_min,
    ROUND((CASE d.basis_kind
        WHEN 'free' THEN 0
        WHEN 'argument' THEN %(price_per_kwh)s::float8 * d.billed_kwh
            + COALESCE(%(session_fee)s::float8, 0)
        WHEN 'geofence_kwh' THEN d.cost_per_unit * d.billed_kwh + COALESCE(d.geofence_fee, 0)
        WHEN 'geofence_minute' THEN d.cost_per_unit * d.duration_min + COALESCE(d.geofence_fee, 0)
        WHEN 'place' THEN d.place_price * d.billed_kwh
        WHEN 'type' THEN d.type_price * d.billed_kwh
    END)::numeric, 2) AS estimated_cost,
    ROUND((CASE d.basis_kind
        WHEN 'free' THEN 0
        WHEN 'argument' THEN %(price_per_kwh)s::float8
        WHEN 'geofence_kwh' THEN d.cost_per_unit
        WHEN 'place' THEN d.place_price
        WHEN 'type' THEN d.type_price
    END)::numeric, 4) AS price_per_kwh,
    CASE d.basis_kind
        WHEN 'free' THEN 'free Supercharging'
        WHEN 'argument' THEN 'price_per_kwh argument'
        WHEN 'geofence_kwh' THEN 'geofence ' || d.geofence_name || ' tariff per kWh'
        WHEN 'geofence_minute' THEN 'geofence ' || d.geofence_name || ' tariff per minute'
        WHEN 'place' THEN 'median price at this location (n=' || d.place_sessions || ')'
        WHEN 'type' THEN 'median ' || REPLACE(d.charger_type, '_', ' ') || ' price (n='
            || d.type_sessions || ')'
    END AS basis
FROM decided d
ORDER BY d.start_date DESC;
