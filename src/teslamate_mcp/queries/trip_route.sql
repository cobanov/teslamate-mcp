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
route AS (
    SELECT p.date,
        p.latitude,
        p.longitude,
        p.battery_level,
        p.speed,
        p.odometer,
        p.elevation,
        t.leg,
        t.drive_id,
        CASE
            WHEN t.leg = 1 THEN 'start'
            WHEN t.charged_before THEN 'charging_stop'
            ELSE 'stop'
        END AS stop_before,
        CASE WHEN t.leg > 1 THEN ROUND(t.stop_before_min::numeric) END AS stop_before_min,
        NTILE(%(max_points)s::int) OVER (ORDER BY p.date) AS bucket
    FROM this_trip t
        JOIN positions p ON p.car_id = t.car_id
            AND p.date BETWEEN t.start_date AND t.end_date
    WHERE p.latitude IS NOT NULL
        AND p.longitude IS NOT NULL
)
-- Buckets never straddle a stop: one point per (leg, bucket).
SELECT ROW_NUMBER() OVER (ORDER BY MIN(date)) AS point_order,
    leg,
    MIN(drive_id) AS drive_id,
    MIN(stop_before) AS stop_before,
    MIN(stop_before_min) AS stop_before_min,
    MIN(date) AS ts,
    ROUND(AVG(latitude)::numeric, 6) AS latitude,
    ROUND(AVG(longitude)::numeric, 6) AS longitude,
    MIN(battery_level) AS battery_level,
    MAX(speed) AS speed_max_kmh,
    MAX(odometer) AS odometer_km,
    ROUND(AVG(elevation))::int AS elevation_m
FROM route
GROUP BY leg, bucket
ORDER BY point_order;
