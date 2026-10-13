-- What the distance driven would have cost in fuel, against what charging
-- cost over the same window. Charging sessions with no recorded cost are
-- priced at electricity_price_per_kwh when given (billed kWh: the larger of
-- kWh drawn and kWh added); otherwise they are left out and cost_coverage_pct
-- shows how much of the energy the electricity cost covers.
WITH scope_cars AS (
    SELECT c.id,
        c.name
    FROM cars c
    WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
driving AS (
    SELECT d.car_id,
        SUM(d.distance)::float8 AS km
    FROM drives d
    WHERE d.car_id IN (SELECT id FROM scope_cars)
        AND d.end_date IS NOT NULL
        AND d.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
    GROUP BY d.car_id
),
charging AS (
    SELECT cp.car_id,
        COUNT(*) AS sessions,
        SUM(cp.charge_energy_added)::float8 AS kwh_added,
        GREATEST(SUM(GREATEST(cp.charge_energy_used, cp.charge_energy_added)), 0)::float8
            AS kwh_billed,
        COALESCE(SUM(cp.cost), 0)::float8 AS recorded_cost,
        COUNT(*) FILTER (
            WHERE cp.cost IS NULL
                AND GREATEST(cp.charge_energy_used, cp.charge_energy_added) >= 0.1
        ) AS sessions_without_cost,
        COALESCE(SUM(GREATEST(cp.charge_energy_used, cp.charge_energy_added))
            FILTER (WHERE cp.cost IS NULL), 0)::float8 AS kwh_without_cost
    FROM charging_processes cp
    WHERE cp.car_id IN (SELECT id FROM scope_cars)
        AND cp.end_date IS NOT NULL
        AND cp.start_date >= CURRENT_DATE - make_interval(days => %(days)s::int)
    GROUP BY cp.car_id
),
totals AS (
    SELECT c.name AS car_name,
        COALESCE(dr.km, 0) AS km,
        COALESCE(dr.km, 0) * %(fuel_consumption_l_per_100km)s::float8 / 100 AS liters,
        COALESCE(dr.km, 0) * %(fuel_consumption_l_per_100km)s::float8 / 100
            * %(fuel_price_per_liter)s::float8 AS fuel_cost,
        COALESCE(ch.sessions, 0) AS sessions,
        COALESCE(ch.kwh_added, 0) AS kwh_added,
        COALESCE(ch.kwh_billed, 0) AS kwh_billed,
        COALESCE(ch.recorded_cost, 0) AS recorded_cost,
        COALESCE(ch.sessions_without_cost, 0) AS sessions_without_cost,
        COALESCE(ch.kwh_without_cost, 0) AS kwh_without_cost,
        COALESCE(ch.kwh_without_cost, 0) * %(electricity_price_per_kwh)s::float8
            AS estimated_missing_cost
    FROM scope_cars c
        LEFT JOIN driving dr ON dr.car_id = c.id
        LEFT JOIN charging ch ON ch.car_id = c.id
    WHERE dr.car_id IS NOT NULL
        OR ch.car_id IS NOT NULL
)
SELECT t.car_name,
    ROUND(t.km::numeric, 1) AS distance_km,
    ROUND(t.liters::numeric, 1) AS fuel_liters,
    ROUND(t.fuel_cost::numeric, 2) AS fuel_cost,
    t.sessions AS charging_sessions,
    ROUND(t.kwh_added::numeric, 1) AS kwh_added,
    ROUND(t.recorded_cost::numeric, 2) AS recorded_charging_cost,
    t.sessions_without_cost,
    ROUND(t.estimated_missing_cost::numeric, 2) AS estimated_missing_cost,
    ROUND((t.recorded_cost + COALESCE(t.estimated_missing_cost, 0))::numeric, 2)
        AS electricity_cost,
    ROUND((100 * (t.kwh_billed - CASE
            WHEN t.estimated_missing_cost IS NULL THEN t.kwh_without_cost
            ELSE 0
        END) / NULLIF(t.kwh_billed, 0))::numeric, 1) AS cost_coverage_pct,
    ROUND((t.fuel_cost - t.recorded_cost - COALESCE(t.estimated_missing_cost, 0))::numeric, 2)
        AS savings,
    ROUND(((t.recorded_cost + COALESCE(t.estimated_missing_cost, 0)) * 100
        / NULLIF(t.km, 0))::numeric, 2) AS electricity_cost_per_100km,
    ROUND((t.fuel_cost * 100 / NULLIF(t.km, 0))::numeric, 2) AS fuel_cost_per_100km
FROM totals t
ORDER BY t.car_name;
