-- Latest position per car via a LATERAL top-1; see battery_health_summary.sql
-- for why the correlated MAX(date) subquery this replaces could not complete
-- on a large positions table.
--
-- Climate and tire values come from their own latest non-null rows. Most
-- in-drive rows have neither, so the latest row alone often reads null.
-- TeslaMate fills climate, tires, and ideal range only on polled rows, so the
-- ideal-range test lets both lookups use TeslaMate's partial (car_id, date)
-- index. Without it the plan cost passes jit_above_cost, and JIT adds about
-- 400 ms. The search stops 7 days before the latest row, so a car that never
-- reports tires does not scan its whole history.
SELECT c.name as car_name,
    p.battery_level,
    p.rated_battery_range_km,
    p.odometer,
    p.outside_temp,
    p.is_climate_on,
    cl.inside_temp,
    cl.driver_temp_setting,
    cl.passenger_temp_setting,
    cl.fan_status,
    cl.is_front_defroster_on,
    cl.is_rear_defroster_on,
    cl.date AS climate_at,
    tp.tpms_pressure_fl,
    tp.tpms_pressure_fr,
    tp.tpms_pressure_rl,
    tp.tpms_pressure_rr,
    tp.date AS tpms_at,
    p.latitude,
    p.longitude,
    a.display_name as location,
    a.city,
    a.state,
    p.date as last_update,
    CASE
        WHEN st.state = 'online' AND drv.start_date IS NOT NULL THEN 'driving'
        WHEN st.state = 'online' AND chg.start_date IS NOT NULL THEN 'charging'
        ELSE st.state
    END AS car_state,
    CASE
        WHEN st.state = 'online' AND drv.start_date IS NOT NULL THEN drv.start_date
        WHEN st.state = 'online' AND chg.start_date IS NOT NULL THEN chg.start_date
        ELSE st.start_date
    END AS car_state_since
FROM cars c
    CROSS JOIN LATERAL (
        SELECT *
        FROM positions p
        WHERE p.car_id = c.id
        ORDER BY p.date DESC
        LIMIT 1
    ) p
    LEFT JOIN LATERAL (
        SELECT pc.date,
            pc.inside_temp,
            pc.driver_temp_setting,
            pc.passenger_temp_setting,
            pc.fan_status,
            pc.is_front_defroster_on,
            pc.is_rear_defroster_on
        FROM positions pc
        WHERE pc.car_id = c.id
            AND pc.ideal_battery_range_km IS NOT NULL
            AND pc.inside_temp IS NOT NULL
            AND pc.date >= p.date - interval '7 days'
        ORDER BY pc.date DESC
        LIMIT 1
    ) cl ON true
    LEFT JOIN LATERAL (
        SELECT pt.date,
            pt.tpms_pressure_fl,
            pt.tpms_pressure_fr,
            pt.tpms_pressure_rl,
            pt.tpms_pressure_rr
        FROM positions pt
        WHERE pt.car_id = c.id
            AND pt.ideal_battery_range_km IS NOT NULL
            AND COALESCE(
                pt.tpms_pressure_fl, pt.tpms_pressure_fr,
                pt.tpms_pressure_rl, pt.tpms_pressure_rr
            ) IS NOT NULL
            AND pt.date >= p.date - interval '7 days'
        ORDER BY pt.date DESC
        LIMIT 1
    ) tp ON true
    LEFT JOIN LATERAL (
        SELECT *
        FROM addresses a
        ORDER BY (
                (p.latitude - a.latitude) ^ 2 + (p.longitude - a.longitude) ^ 2
            )
        LIMIT 1
    ) a ON true
    LEFT JOIN LATERAL (
        SELECT s.state::text AS state,
            s.start_date
        FROM states s
        WHERE s.car_id = c.id
            AND s.end_date IS NULL
        ORDER BY s.start_date DESC
        LIMIT 1
    ) st ON true
    -- Driving: the latest position belongs to a drive that has not ended, and
    -- is recent. TeslaMate leaves drives open when it restarts mid-drive, so
    -- an open drive alone does not mean the car is moving.
    LEFT JOIN LATERAL (
        SELECT d.start_date
        FROM drives d
        WHERE d.id = p.drive_id
            AND d.end_date IS NULL
            AND p.date >= (now() AT TIME ZONE 'UTC') - interval '30 minutes'
    ) drv ON true
    LEFT JOIN LATERAL (
        SELECT cp.start_date
        FROM charging_processes cp
        WHERE cp.car_id = c.id
            AND cp.end_date IS NULL
            AND cp.start_date >= st.start_date
        ORDER BY cp.start_date DESC
        LIMIT 1
    ) chg ON true
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%');
