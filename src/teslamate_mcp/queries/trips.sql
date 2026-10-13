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
        d.end_address_id,
        d.ascent,
        d.descent
    FROM drives d
        JOIN cars c ON c.id = d.car_id
    WHERE d.end_date IS NOT NULL
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
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
summary AS (
    SELECT t.car_id,
        t.trip_id,
        MIN(t.car_name) AS car_name,
        MIN(t.start_date) AS start_date,
        MAX(t.end_date) AS end_date,
        COUNT(*) AS legs,
        COUNT(*) FILTER (WHERE t.starts_trip = 0 AND t.charged_before) AS charging_stops,
        SUM(t.distance) AS distance_km,
        SUM(t.duration_min) AS driving_min,
        COALESCE(SUM(t.stop_before_min) FILTER (WHERE t.starts_trip = 0), 0) AS stopped_min,
        MAX(t.speed_max) AS speed_max_kmh,
        SUM(t.start_rated_range_km - t.end_rated_range_km) AS rated_range_used_km,
        SUM(t.ascent) AS ascent_m,
        SUM(t.descent) AS descent_m,
        SUM(t.outside_temp_avg * t.duration_min) FILTER (WHERE t.outside_temp_avg IS NOT NULL)
            / NULLIF(SUM(t.duration_min) FILTER (WHERE t.outside_temp_avg IS NOT NULL), 0)
            AS outside_temp_avg,
        (ARRAY_AGG(t.start_address_id ORDER BY t.start_date))[1] AS start_address_id,
        (ARRAY_AGG(t.end_address_id ORDER BY t.start_date DESC))[1] AS end_address_id,
        ARRAY_AGG(t.start_address_id) || ARRAY_AGG(t.end_address_id) AS address_ids
    FROM tripped t
    GROUP BY t.car_id, t.trip_id
),
filtered AS (
    SELECT s.*
    FROM summary s
    WHERE (%(start_date)s::date IS NULL
            OR ((s.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date
                >= %(start_date)s::date)
        AND (%(end_date)s::date IS NULL
            OR ((s.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date
                <= %(end_date)s::date)
        AND (%(min_distance_km)s::float8 IS NULL OR s.distance_km >= %(min_distance_km)s)
        AND (%(min_legs)s::int IS NULL OR s.legs >= %(min_legs)s::int)
        AND (%(location)s::text IS NULL OR EXISTS (
            SELECT 1
            FROM addresses a
            WHERE a.id = ANY (s.address_ids)
                AND (a.display_name ILIKE '%%' || %(location)s || '%%'
                    OR a.city ILIKE '%%' || %(location)s || '%%')
        ))
    ORDER BY CASE
            WHEN %(order_by)s::text = 'distance' THEN s.distance_km
            WHEN %(order_by)s::text = 'duration' THEN EXTRACT(EPOCH FROM (s.end_date - s.start_date))
        END DESC NULLS LAST,
        s.start_date DESC
    LIMIT %(limit)s::int
)
SELECT f.trip_id,
    f.car_name,
    f.start_date,
    f.end_date,
    f.legs,
    f.legs - 1 AS stops,
    f.charging_stops,
    ROUND(f.distance_km::numeric, 1) AS distance_km,
    f.driving_min,
    ROUND((EXTRACT(EPOCH FROM (f.end_date - f.start_date)) / 60.0)::numeric) AS total_min,
    ROUND(f.stopped_min::numeric) AS stopped_min,
    ROUND((f.distance_km / NULLIF(f.driving_min, 0) * 60)::numeric, 1) AS avg_moving_speed_kmh,
    f.speed_max_kmh,
    sa.display_name AS start_location,
    sa.city AS start_city,
    ea.display_name AS end_location,
    ea.city AS end_city,
    first_pos.battery_level AS start_battery_level,
    last_pos.battery_level AS end_battery_level,
    ROUND(energy.added_kwh::numeric, 1) AS energy_added_kwh,
    ROUND(f.rated_range_used_km::numeric, 1) AS rated_range_used_km,
    ROUND(f.outside_temp_avg::numeric, 1) AS outside_temp_avg,
    f.ascent_m,
    f.descent_m
FROM filtered f
    LEFT JOIN addresses sa ON sa.id = f.start_address_id
    LEFT JOIN addresses ea ON ea.id = f.end_address_id
    LEFT JOIN LATERAL (
        SELECT p.battery_level
        FROM positions p
        WHERE p.car_id = f.car_id
            AND p.date >= f.start_date
            AND p.date <= f.end_date
            AND p.battery_level IS NOT NULL
        ORDER BY p.date
        LIMIT 1
    ) first_pos ON TRUE
    LEFT JOIN LATERAL (
        SELECT p.battery_level
        FROM positions p
        WHERE p.car_id = f.car_id
            AND p.date >= f.start_date
            AND p.date <= f.end_date
            AND p.battery_level IS NOT NULL
        ORDER BY p.date DESC
        LIMIT 1
    ) last_pos ON TRUE
    LEFT JOIN LATERAL (
        SELECT SUM(cp.charge_energy_added) AS added_kwh
        FROM charging_processes cp
        WHERE cp.car_id = f.car_id
            AND cp.start_date >= f.start_date
            AND cp.start_date < f.end_date
    ) energy ON TRUE
ORDER BY CASE
        WHEN %(order_by)s::text = 'distance' THEN f.distance_km
        WHEN %(order_by)s::text = 'duration' THEN EXTRACT(EPOCH FROM (f.end_date - f.start_date))
    END DESC NULLS LAST,
    f.start_date DESC;
