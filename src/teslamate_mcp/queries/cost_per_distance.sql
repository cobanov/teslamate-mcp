-- What driving costs per local month: the distance driven against the charging
-- that month, split into AC and DC. A session is DC when a charge sample came
-- from a fast charger, as in get_charging_efficiency. Prices per kWh only count
-- sessions with a recorded cost, so a month with unpriced sessions still shows
-- a fair price; cost_per_100km uses the recorded cost and undercounts then.
WITH scope_cars AS (
    SELECT id, name
    FROM cars
    WHERE (%(car_name)s::text IS NULL OR name ILIKE '%%' || %(car_name)s || '%%')
),
driving AS (
    SELECT d.car_id,
        DATE_TRUNC('month', (d.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text) AS month,
        SUM(d.distance) AS km
    FROM drives d
    WHERE d.car_id IN (SELECT id FROM scope_cars)
        AND d.end_date IS NOT NULL
        AND d.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
    GROUP BY 1, 2
),
sessions AS (
    SELECT cp.car_id,
        DATE_TRUNC('month', (cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text) AS month,
        cp.charge_energy_added AS kwh,
        cp.cost,
        EXISTS (
            SELECT 1
            FROM charges ch
            WHERE ch.charging_process_id = cp.id
                AND (ch.fast_charger_present OR (ch.charger_phases IS NULL AND ch.charger_power > 0))
        ) AS is_dc
    FROM charging_processes cp
    WHERE cp.car_id IN (SELECT id FROM scope_cars)
        AND cp.end_date IS NOT NULL
        AND cp.charge_energy_added > 0
        AND cp.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
),
charging AS (
    SELECT car_id,
        month,
        COUNT(*) AS sessions,
        COUNT(*) FILTER (WHERE cost IS NULL) AS sessions_without_cost,
        SUM(kwh) AS kwh,
        SUM(kwh) FILTER (WHERE NOT is_dc) AS ac_kwh,
        SUM(kwh) FILTER (WHERE is_dc) AS dc_kwh,
        SUM(cost) AS cost,
        SUM(cost) FILTER (WHERE NOT is_dc) / NULLIF(SUM(kwh) FILTER (WHERE NOT is_dc AND cost IS NOT NULL), 0)
            AS ac_price,
        SUM(cost) FILTER (WHERE is_dc) / NULLIF(SUM(kwh) FILTER (WHERE is_dc AND cost IS NOT NULL), 0)
            AS dc_price,
        SUM(cost) / NULLIF(SUM(kwh) FILTER (WHERE cost IS NOT NULL), 0) AS price
    FROM sessions
    GROUP BY car_id, month
)
SELECT TO_CHAR(COALESCE(dr.month, ch.month), 'YYYY-MM') AS month,
    c.name AS car_name,
    ROUND(COALESCE(dr.km, 0)::numeric, 1) AS distance_km,
    COALESCE(ch.sessions, 0) AS sessions,
    COALESCE(ch.sessions_without_cost, 0) AS sessions_without_cost,
    ROUND(COALESCE(ch.kwh, 0)::numeric, 1) AS energy_added_kwh,
    ROUND(COALESCE(ch.ac_kwh, 0)::numeric, 1) AS ac_kwh,
    ROUND(COALESCE(ch.dc_kwh, 0)::numeric, 1) AS dc_kwh,
    ROUND(ch.cost::numeric, 2) AS cost,
    ROUND(ch.ac_price::numeric, 3) AS ac_cost_per_kwh,
    ROUND(ch.dc_price::numeric, 3) AS dc_cost_per_kwh,
    ROUND(ch.price::numeric, 3) AS cost_per_kwh,
    ROUND((ch.cost * 100 / NULLIF(dr.km, 0))::numeric, 2) AS cost_per_100km,
    ROUND((ch.kwh * 100 / NULLIF(dr.km, 0))::numeric, 1) AS kwh_charged_per_100km
FROM driving dr
    FULL JOIN charging ch ON ch.car_id = dr.car_id AND ch.month = dr.month
    JOIN scope_cars c ON c.id = COALESCE(dr.car_id, ch.car_id)
ORDER BY c.name, 1 DESC;
