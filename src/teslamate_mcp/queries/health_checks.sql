-- One row per car and check, worst first: is TeslaMate still logging, are
-- drives or charges left open, tire pressures, parked drain, time awake while
-- parked, charges left sitting near 100 %%, range lost since new, and the
-- battery level now.
--
-- The windows end at the car's last logged position rather than now(), so a
-- car TeslaMate lost touch with still gets its last week judged; last_data
-- says how old that is. The latest position uses the partial index TeslaMate
-- keeps on (car_id, date) WHERE ideal_battery_range_km IS NOT NULL.
WITH scope_cars AS (
    SELECT id, name
    FROM cars
    WHERE (%(car_name)s::text IS NULL OR name ILIKE '%%' || %(car_name)s || '%%')
),
seen AS (
    SELECT sc.id AS car_id,
        last.date AS at,
        last.battery_level,
        st.state,
        st.start_date AS state_since
    FROM scope_cars sc
        LEFT JOIN LATERAL (
            SELECT p.date, p.battery_level
            FROM positions p
            WHERE p.car_id = sc.id
                AND p.ideal_battery_range_km IS NOT NULL
            ORDER BY p.date DESC
            LIMIT 1
        ) last ON TRUE
        LEFT JOIN LATERAL (
            SELECT s.state::text AS state, s.start_date
            FROM states s
            WHERE s.car_id = sc.id
            ORDER BY s.start_date DESC
            LIMIT 1
        ) st ON TRUE
),
last_data AS (
    SELECT s.car_id,
        EXTRACT(EPOCH FROM ((now() AT TIME ZONE 'UTC') - s.at)) / 86400 AS days,
        s.at,
        s.state,
        s.state_since
    FROM seen s
),
-- A drive or charge started in the last 6 hours may simply still be running.
open_rows AS (
    SELECT sc.id AS car_id,
        (SELECT COUNT(*) FROM drives d
            WHERE d.car_id = sc.id AND d.end_date IS NULL
                AND d.start_date < (now() AT TIME ZONE 'UTC') - INTERVAL '6 hours') AS drives,
        (SELECT COUNT(*) FROM charging_processes cp
            WHERE cp.car_id = sc.id AND cp.end_date IS NULL
                AND cp.start_date < (now() AT TIME ZONE 'UTC') - INTERVAL '6 hours') AS charges
    FROM scope_cars sc
),
-- Tires: the week before the newest reading against the week four weeks
-- earlier. Cold lowers all four alike, so a slow leak shows as one tire
-- dropping more than the others.
tire_base AS (
    SELECT sc.id AS car_id, t.date AS at
    FROM scope_cars sc
        CROSS JOIN LATERAL (
            SELECT p.date
            FROM positions p
            WHERE p.car_id = sc.id
                AND p.ideal_battery_range_km IS NOT NULL
                AND p.tpms_pressure_fl IS NOT NULL
            ORDER BY p.date DESC
            LIMIT 1
        ) t
),
tire_weeks AS (
    SELECT tb.car_id,
        AVG(p.tpms_pressure_fl) FILTER (WHERE p.date > tb.at - INTERVAL '7 days') AS fl,
        AVG(p.tpms_pressure_fr) FILTER (WHERE p.date > tb.at - INTERVAL '7 days') AS fr,
        AVG(p.tpms_pressure_rl) FILTER (WHERE p.date > tb.at - INTERVAL '7 days') AS rl,
        AVG(p.tpms_pressure_rr) FILTER (WHERE p.date > tb.at - INTERVAL '7 days') AS rr,
        AVG(p.tpms_pressure_fl) FILTER (WHERE p.date <= tb.at - INTERVAL '28 days') AS fl0,
        AVG(p.tpms_pressure_fr) FILTER (WHERE p.date <= tb.at - INTERVAL '28 days') AS fr0,
        AVG(p.tpms_pressure_rl) FILTER (WHERE p.date <= tb.at - INTERVAL '28 days') AS rl0,
        AVG(p.tpms_pressure_rr) FILTER (WHERE p.date <= tb.at - INTERVAL '28 days') AS rr0
    FROM tire_base tb
        JOIN positions p ON p.car_id = tb.car_id
            AND p.ideal_battery_range_km IS NOT NULL
            AND p.tpms_pressure_fl IS NOT NULL
            AND p.date <= tb.at
            AND (p.date > tb.at - INTERVAL '7 days'
                OR p.date BETWEEN tb.at - INTERVAL '35 days' AND tb.at - INTERVAL '28 days')
    GROUP BY tb.car_id
),
tires AS (
    SELECT tw.*,
        GREATEST(fl, fr, rl, rr) - LEAST(fl, fr, rl, rr) AS spread,
        GREATEST(fl0 - fl, fr0 - fr, rl0 - rl, rr0 - rr)
            - LEAST(fl0 - fl, fr0 - fr, rl0 - rl, rr0 - rr) AS leak_gap
    FROM tire_weeks tw
),
-- Rated range lost while parked 5 h or more without charging, as in
-- get_vampire_drain, over the last 30 days of data.
parked AS (
    SELECT d.car_id,
        d.end_date AS gap_start,
        LEAD(d.start_date) OVER w AS gap_end,
        d.end_rated_range_km - LEAD(d.start_rated_range_km) OVER w AS loss_km
    FROM drives d
    WHERE d.car_id IN (SELECT id FROM scope_cars)
        AND d.end_date IS NOT NULL
    WINDOW w AS (PARTITION BY d.car_id ORDER BY d.start_date)
),
drain AS (
    SELECT p.car_id,
        COUNT(*) AS gaps,
        SUM(p.loss_km) / NULLIF(SUM(EXTRACT(EPOCH FROM (p.gap_end - p.gap_start))) / 86400, 0)
            AS km_per_day
    FROM parked p
        JOIN seen s ON s.car_id = p.car_id
    WHERE p.gap_end IS NOT NULL
        AND p.gap_start >= s.at - INTERVAL '30 days'
        AND p.gap_end - p.gap_start >= INTERVAL '5 hours'
        AND p.loss_km >= 0
        AND NOT EXISTS (
            SELECT 1
            FROM charging_processes cp
            WHERE cp.car_id = p.car_id
                AND cp.start_date <= p.gap_end
                AND COALESCE(cp.end_date, p.gap_end) >= p.gap_start
        )
    GROUP BY p.car_id
),
-- Online time in the last 7 days of data, minus driving and charging.
awake AS (
    SELECT s.car_id,
        GREATEST(0,
            COALESCE((SELECT SUM(EXTRACT(EPOCH FROM (
                    LEAST(COALESCE(st.end_date, s.at), s.at)
                    - GREATEST(st.start_date, s.at - INTERVAL '7 days'))))
                FROM states st
                WHERE st.car_id = s.car_id
                    AND st.state::text = 'online'
                    AND st.start_date < s.at
                    AND COALESCE(st.end_date, s.at) > s.at - INTERVAL '7 days'), 0)
            - COALESCE((SELECT SUM(EXTRACT(EPOCH FROM (
                    LEAST(d.end_date, s.at) - GREATEST(d.start_date, s.at - INTERVAL '7 days'))))
                FROM drives d
                WHERE d.car_id = s.car_id
                    AND d.end_date IS NOT NULL
                    AND d.start_date < s.at
                    AND d.end_date > s.at - INTERVAL '7 days'), 0)
            - COALESCE((SELECT SUM(EXTRACT(EPOCH FROM (
                    LEAST(cp.end_date, s.at) - GREATEST(cp.start_date, s.at - INTERVAL '7 days'))))
                FROM charging_processes cp
                WHERE cp.car_id = s.car_id
                    AND cp.end_date IS NOT NULL
                    AND cp.start_date < s.at
                    AND cp.end_date > s.at - INTERVAL '7 days'), 0)
        ) / 7 / 3600 AS hours_per_day
    FROM seen s
    WHERE s.at IS NOT NULL
),
-- Charges in the last 30 days of data that ended at 95 %% or more and then
-- sat 12 hours or more before the next drive.
full_sits AS (
    SELECT s.car_id,
        COUNT(*) FILTER (
            WHERE COALESCE(nd.start_date, s.at) - cp.end_date >= INTERVAL '12 hours'
        ) AS sits,
        COUNT(*) AS full_charges
    FROM seen s
        JOIN charging_processes cp ON cp.car_id = s.car_id
        LEFT JOIN LATERAL (
            SELECT d.start_date
            FROM drives d
            WHERE d.car_id = cp.car_id
                AND d.start_date >= cp.end_date
            ORDER BY d.start_date
            LIMIT 1
        ) nd ON TRUE
    WHERE cp.end_date IS NOT NULL
        AND cp.end_battery_level >= 95
        AND cp.end_date >= s.at - INTERVAL '30 days'
    GROUP BY s.car_id
),
-- Rated range at 100 %% from charges that ended at 50 %% or more: the five
-- newest against the first ten the car logged.
range_readings AS (
    SELECT cp.car_id,
        cp.end_rated_range_km * 100 / cp.end_battery_level AS range_at_100,
        ROW_NUMBER() OVER (PARTITION BY cp.car_id ORDER BY cp.end_date) AS oldest,
        ROW_NUMBER() OVER (PARTITION BY cp.car_id ORDER BY cp.end_date DESC) AS newest
    FROM charging_processes cp
    WHERE cp.car_id IN (SELECT id FROM scope_cars)
        AND cp.end_date IS NOT NULL
        AND cp.end_battery_level >= 50
        AND cp.end_rated_range_km > 0
),
range_loss AS (
    SELECT car_id,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY range_at_100)
            FILTER (WHERE oldest <= 10) AS first_km,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY range_at_100)
            FILTER (WHERE newest <= 5) AS now_km,
        COUNT(*) AS readings
    FROM range_readings
    GROUP BY car_id
    -- Under 15 readings the first and newest charges overlap.
    HAVING COUNT(*) >= 15
),
checks AS (
    SELECT ld.car_id,
        'last_data' AS check_name,
        CASE
            WHEN ld.at IS NULL THEN 'alert'
            WHEN ld.days < 2 THEN 'ok'
            WHEN ld.days < 7 THEN CASE WHEN ld.state = 'asleep' THEN 'ok' ELSE 'warn' END
            ELSE CASE WHEN ld.state = 'asleep' THEN 'warn' ELSE 'alert' END
        END AS status,
        ROUND(ld.days::numeric, 1) AS value,
        'days' AS unit,
        CASE WHEN ld.at IS NULL THEN 'TeslaMate has no position for this car.'
        ELSE format('Last position %%s UTC; the car has been %%s since %%s UTC. A car asleep logs '
            'nothing, so a long gap while it is asleep can be normal; a long gap offline or '
            'online usually means TeslaMate lost the car (token, connectivity, container down).',
            TO_CHAR(ld.at, 'YYYY-MM-DD HH24:MI'), COALESCE(ld.state, 'unknown'),
            TO_CHAR(ld.state_since, 'YYYY-MM-DD HH24:MI'))
        END AS detail
    FROM last_data ld
    UNION ALL
    SELECT o.car_id,
        'open_records',
        CASE WHEN o.drives + o.charges = 0 THEN 'ok' ELSE 'warn' END,
        o.drives + o.charges,
        'rows',
        format('%%s drives and %%s charges have no end (TeslaMate lost the car mid-way); most '
            'reports skip them. get_logging_gaps lists them.', o.drives, o.charges)
    FROM open_rows o
    UNION ALL
    SELECT sc.id,
        'tire_pressure',
        CASE
            WHEN t.fl IS NULL THEN 'unknown'
            WHEN t.spread >= 0.35 OR t.leak_gap >= 0.25 THEN 'alert'
            WHEN t.spread >= 0.2 OR t.leak_gap >= 0.15 THEN 'warn'
            ELSE 'ok'
        END,
        ROUND(GREATEST(t.spread, COALESCE(t.leak_gap, 0))::numeric, 2),
        'bar',
        CASE WHEN t.fl IS NULL THEN 'No tire pressure readings.'
        ELSE format('Last week of readings: FL %%s, FR %%s, RL %%s, RR %%s bar (spread %%s). '
            'Change from four weeks earlier: FL %%s, FR %%s, RL %%s, RR %%s bar. One tire '
            'dropping more than the others points to a slow leak.',
            ROUND(t.fl::numeric, 2), ROUND(t.fr::numeric, 2), ROUND(t.rl::numeric, 2),
            ROUND(t.rr::numeric, 2), ROUND(t.spread::numeric, 2),
            COALESCE(ROUND((t.fl - t.fl0)::numeric, 2)::text, 'n/a'),
            COALESCE(ROUND((t.fr - t.fr0)::numeric, 2)::text, 'n/a'),
            COALESCE(ROUND((t.rl - t.rl0)::numeric, 2)::text, 'n/a'),
            COALESCE(ROUND((t.rr - t.rr0)::numeric, 2)::text, 'n/a'))
        END
    FROM scope_cars sc
        LEFT JOIN tires t ON t.car_id = sc.id
    UNION ALL
    SELECT sc.id,
        'parked_drain',
        CASE
            WHEN dr.km_per_day IS NULL THEN 'unknown'
            WHEN dr.km_per_day < 5 THEN 'ok'
            WHEN dr.km_per_day < 10 THEN 'warn'
            ELSE 'alert'
        END,
        ROUND(dr.km_per_day::numeric, 1),
        'km/day',
        CASE WHEN dr.km_per_day IS NULL
            THEN 'No parked stretch of 5 h or more without charging in the last 30 days of data.'
        ELSE format('Rated range lost while parked, over %%s stretches of 5 h or more without '
            'charging in the last 30 days of data. Sentry Mode, apps waking the car, and '
            'climate raise it; get_vampire_drain lists the worst.', dr.gaps)
        END
    FROM scope_cars sc
        LEFT JOIN drain dr ON dr.car_id = sc.id
    UNION ALL
    SELECT sc.id,
        'idle_awake',
        CASE
            WHEN a.hours_per_day IS NULL THEN 'unknown'
            WHEN a.hours_per_day < 3 THEN 'ok'
            WHEN a.hours_per_day < 8 THEN 'warn'
            ELSE 'alert'
        END,
        ROUND(a.hours_per_day::numeric, 1),
        'h/day',
        'Hours a day the car stayed awake while parked and not charging, over the last 7 days '
            'of data. An awake car drains about 1 kWh an hour more than a sleeping one; '
            'get_idle_awake_periods shows when and where.'
    FROM scope_cars sc
        LEFT JOIN awake a ON a.car_id = sc.id
    UNION ALL
    SELECT sc.id,
        'full_charge_sits',
        CASE WHEN COALESCE(f.sits, 0) < 2 THEN 'ok' ELSE 'warn' END,
        COALESCE(f.sits, 0),
        'charges',
        format('%%s of %%s charges to 95 %%%% or more in the last 30 days of data then sat 12 h or '
            'more before driving. Sitting full ages an NCA/NCM battery faster; an LFP battery '
            '(most Standard Range cars) is meant to reach 100 %%%% weekly, so ignore this for one.',
            COALESCE(f.sits, 0), COALESCE(f.full_charges, 0))
    FROM scope_cars sc
        LEFT JOIN full_sits f ON f.car_id = sc.id
    UNION ALL
    SELECT sc.id,
        'range_loss',
        CASE
            WHEN rl.first_km IS NULL THEN 'unknown'
            WHEN 100 * (1 - rl.now_km / rl.first_km) < 10 THEN 'ok'
            WHEN 100 * (1 - rl.now_km / rl.first_km) < 20 THEN 'warn'
            ELSE 'alert'
        END,
        ROUND((100 * (1 - rl.now_km / rl.first_km))::numeric, 1),
        '%%',
        CASE WHEN rl.first_km IS NULL THEN 'Needs 15 charges that ended at 50 %% or more.'
        ELSE format('Rated range at 100 %%%%: %%s km now (newest 5 charges) against %%s km from the '
            'first 10 charges. Up to about 10 %%%% in the first 100,000 km is typical; '
            'get_projected_range_by_mileage has the curve.',
            ROUND(rl.now_km::numeric, 1), ROUND(rl.first_km::numeric, 1))
        END
    FROM scope_cars sc
        LEFT JOIN range_loss rl ON rl.car_id = sc.id
    UNION ALL
    SELECT s.car_id,
        'battery_level',
        CASE
            WHEN s.battery_level IS NULL THEN 'unknown'
            WHEN s.battery_level >= 20 THEN 'ok'
            WHEN s.battery_level >= 10 THEN 'warn'
            ELSE 'alert'
        END,
        s.battery_level,
        '%%',
        'Battery level at the last logged position.'
    FROM seen s
)
SELECT sc.name AS car_name,
    ch.check_name,
    ch.status,
    ch.value,
    ch.unit,
    ch.detail
FROM checks ch
    JOIN scope_cars sc ON sc.id = ch.car_id
ORDER BY sc.name,
    CASE ch.status WHEN 'alert' THEN 0 WHEN 'warn' THEN 1 WHEN 'unknown' THEN 2 ELSE 3 END,
    ch.check_name;
