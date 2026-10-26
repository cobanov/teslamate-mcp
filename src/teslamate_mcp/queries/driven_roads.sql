-- Every road the car has driven, as downsampled paths, one row per car. A
-- commute driven 300 times draws the same line 300 times, so only the newest
-- drive between each pair of places (~500 m cells, either direction) is
-- kept. The point budget is spread over the kept drives by keeping every Nth
-- sample (by id, which TeslaMate assigns in time order), plus each drive's
-- first and last position so every path has both ends.
WITH keyed AS (
    SELECT d.id,
        d.car_id,
        d.start_date,
        d.distance,
        d.start_position_id,
        d.end_position_id,
        ROUND(sp.latitude * 200) || ':' || ROUND(sp.longitude * 200) AS start_cell,
        ROUND(ep.latitude * 200) || ':' || ROUND(ep.longitude * 200) AS end_cell
    FROM drives d
        JOIN cars c ON c.id = d.car_id
        LEFT JOIN positions sp ON sp.id = d.start_position_id
        LEFT JOIN positions ep ON ep.id = d.end_position_id
    WHERE d.end_date IS NOT NULL
        AND d.distance >= %(min_distance_km)s::float8
        AND (%(days)s::int IS NULL OR d.start_date >= CURRENT_DATE - make_interval(days => %(days)s))
        AND (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
),
chosen AS (
    SELECT *
    FROM (
        SELECT k.*,
            ROW_NUMBER() OVER (
                -- A drive without position ids is its own route.
                PARTITION BY k.car_id,
                    COALESCE(LEAST(k.start_cell, k.end_cell), 'drive ' || k.id),
                    GREATEST(k.start_cell, k.end_cell)
                ORDER BY k.start_date DESC
            ) AS newest
        FROM keyed k
    ) ranked
    WHERE newest = 1
),
sampling AS (
    SELECT GREATEST(1, CEIL(COUNT(*) / %(max_points)s::float8))::int AS every
    FROM positions
    WHERE drive_id IN (SELECT id FROM chosen)
),
-- Coordinates as integers in 1e-4 degrees (about 10 m): each drive starts
-- with its first point and goes on in steps from the point before, which
-- roughly halves the text a map of every road takes.
points AS (
    SELECT p.drive_id,
        p.date,
        p.id,
        ROUND(p.longitude * 10000)::int AS x,
        ROUND(p.latitude * 10000)::int AS y
    FROM positions p
        CROSS JOIN sampling s
    WHERE p.drive_id IN (SELECT id FROM chosen)
        AND p.latitude IS NOT NULL
        AND (p.id %% s.every = 0
            OR p.id IN (SELECT start_position_id FROM chosen)
            OR p.id IN (SELECT end_position_id FROM chosen))
),
coded AS (
    SELECT drive_id,
        date,
        id,
        CASE WHEN LAG(x) OVER w IS NULL THEN x || ',' || y
            ELSE (x - LAG(x) OVER w) || ',' || (y - LAG(y) OVER w)
        END AS code
    FROM points
    WINDOW w AS (PARTITION BY drive_id ORDER BY date, id)
),
paths AS (
    SELECT drive_id, COUNT(*) AS points, STRING_AGG(code, ' ' ORDER BY date, id) AS path
    FROM coded
    GROUP BY drive_id
    HAVING COUNT(*) >= 2
)
SELECT c.name AS car_name,
    COUNT(*) AS routes,
    ROUND(SUM(ch.distance)::numeric, 1) AS distance_km,
    SUM(pa.points) AS points,
    MIN(ch.start_date) AS first_drive,
    MAX(ch.start_date) AS last_drive,
    STRING_AGG(pa.path, ';' ORDER BY ch.start_date) AS paths
FROM chosen ch
    JOIN paths pa ON pa.drive_id = ch.id
    JOIN cars c ON c.id = ch.car_id
GROUP BY c.name
ORDER BY c.name;
