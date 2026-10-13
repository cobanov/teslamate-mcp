WITH scope AS (
    SELECT d.id AS drive_id,
        d.car_id,
        c.name AS car_name,
        d.start_date,
        d.end_date,
        d.distance,
        d.duration_min,
        d.speed_max,
        d.outside_temp_avg,
        d.start_rated_range_km,
        d.end_rated_range_km,
        d.start_address_id,
        d.end_address_id
    FROM drives d
        JOIN cars c ON c.id = d.car_id
    WHERE d.end_date IS NOT NULL
        AND d.car_id = (SELECT car_id FROM drives WHERE id = %(trip_id)s::int)
),
-- trip grouping: begin (keep identical in trips.sql, trip_details.sql, trip_route.sql)
legs AS (
    SELECT s.*,
        LAG(s.end_date) OVER w AS prev_end,
        LAG(s.end_address_id) OVER w AS prev_end_address_id
    FROM scope s
    WINDOW w AS (PARTITION BY s.car_id ORDER BY s.start_date)
),
stops AS (
    SELECT l.*,
        EXTRACT(EPOCH FROM (l.start_date - l.prev_end)) / 60.0 AS stop_before_min,
        EXISTS (
            SELECT 1
            FROM charging_processes cp
            WHERE cp.car_id = l.car_id
                AND cp.start_date >= l.prev_end
                AND cp.start_date < l.start_date
        ) AS charged_before
    FROM legs l
),
marked AS (
    SELECT st.*,
        CASE
            WHEN st.prev_end IS NULL THEN 1
            WHEN st.stop_before_min > CASE
                    WHEN st.charged_before THEN %(max_charging_stop_minutes)s::float8
                    ELSE %(max_stop_minutes)s::float8
                END THEN 1
            ELSE 0
        END AS starts_trip
    FROM stops st
),
numbered AS (
    SELECT m.*,
        SUM(m.starts_trip) OVER (PARTITION BY m.car_id ORDER BY m.start_date) AS trip_seq
    FROM marked m
),
tripped AS (
    SELECT n.*,
        FIRST_VALUE(n.drive_id) OVER (
            PARTITION BY n.car_id, n.trip_seq ORDER BY n.start_date
        ) AS trip_id
    FROM numbered n
),
-- trip grouping: end
this_trip AS (
    SELECT t.*,
        ROW_NUMBER() OVER (ORDER BY t.start_date) AS leg
    FROM tripped t
    WHERE t.trip_id = (SELECT trip_id FROM tripped WHERE drive_id = %(trip_id)s::int)
),
drive_rows AS (
    SELECT t.start_date AS sort_key,
        0 AS sort_rank,
        t.leg,
        'drive'::text AS kind,
        t.drive_id,
        t.start_date,
        t.end_date,
        t.duration_min::numeric AS duration_min,
        ROUND(t.distance::numeric, 1) AS distance_km,
        sa.display_name AS from_location,
        sa.city AS from_city,
        ea.display_name AS to_location,
        ea.city AS to_city,
        t.speed_max AS speed_max_kmh,
        ROUND((t.start_rated_range_km - t.end_rated_range_km)::numeric, 1) AS rated_range_used_km,
        NULL::numeric AS charge_energy_added_kwh,
        NULL::int AS charge_start_battery_level,
        NULL::int AS charge_end_battery_level
    FROM this_trip t
        LEFT JOIN addresses sa ON sa.id = t.start_address_id
        LEFT JOIN addresses ea ON ea.id = t.end_address_id
),
stop_rows AS (
    SELECT t.prev_end AS sort_key,
        1 AS sort_rank,
        t.leg - 1 AS leg,
        CASE WHEN t.charged_before THEN 'charging_stop' ELSE 'stop' END AS kind,
        NULL::int AS drive_id,
        t.prev_end AS start_date,
        t.start_date AS end_date,
        ROUND(t.stop_before_min::numeric) AS duration_min,
        NULL::numeric AS distance_km,
        COALESCE(ca.display_name, pa.display_name) AS from_location,
        COALESCE(ca.city, pa.city) AS from_city,
        COALESCE(ca.display_name, pa.display_name) AS to_location,
        COALESCE(ca.city, pa.city) AS to_city,
        NULL::int AS speed_max_kmh,
        NULL::numeric AS rated_range_used_km,
        ROUND(chg.added_kwh::numeric, 1) AS charge_energy_added_kwh,
        chg.start_level AS charge_start_battery_level,
        chg.end_level AS charge_end_battery_level
    FROM this_trip t
        LEFT JOIN addresses pa ON pa.id = t.prev_end_address_id
        LEFT JOIN LATERAL (
            SELECT SUM(cp.charge_energy_added) AS added_kwh,
                (ARRAY_AGG(cp.start_battery_level ORDER BY cp.start_date))[1]::int AS start_level,
                (ARRAY_AGG(cp.end_battery_level ORDER BY cp.start_date DESC))[1]::int AS end_level,
                (ARRAY_AGG(cp.address_id ORDER BY cp.start_date))[1] AS address_id
            FROM charging_processes cp
            WHERE t.charged_before
                AND cp.car_id = t.car_id
                AND cp.start_date >= t.prev_end
                AND cp.start_date < t.start_date
        ) chg ON TRUE
        LEFT JOIN addresses ca ON ca.id = chg.address_id
    WHERE t.leg > 1
)
SELECT ROW_NUMBER() OVER (ORDER BY r.sort_key, r.sort_rank) AS seq,
    (SELECT MIN(trip_id) FROM this_trip) AS trip_id,
    r.kind,
    r.leg,
    r.drive_id,
    r.start_date,
    r.end_date,
    r.duration_min,
    r.distance_km,
    r.from_location,
    r.from_city,
    r.to_location,
    r.to_city,
    r.speed_max_kmh,
    r.rated_range_used_km,
    r.charge_energy_added_kwh,
    r.charge_start_battery_level,
    r.charge_end_battery_level
FROM (SELECT * FROM drive_rows UNION ALL SELECT * FROM stop_rows) r
ORDER BY seq;
