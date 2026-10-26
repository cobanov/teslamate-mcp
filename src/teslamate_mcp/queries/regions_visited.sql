-- Countries, states, and cities the car has been to, from the reverse-geocoded
-- addresses of where drives ended and charges happened. level rolls the rows
-- up: at 'country' the state and city are null, at 'state' the city is.
WITH scope_cars AS (
    SELECT id
    FROM cars
    WHERE (%(car_name)s::text IS NULL OR name ILIKE '%%' || %(car_name)s || '%%')
),
visits AS (
    SELECT d.end_address_id AS address_id, d.end_date AS at, 'arrival' AS kind
    FROM drives d
    WHERE d.car_id IN (SELECT id FROM scope_cars)
        AND d.end_date IS NOT NULL
        AND (%(days)s::int IS NULL OR d.start_date >= CURRENT_DATE - make_interval(days => %(days)s))
    UNION ALL
    SELECT cp.address_id, cp.start_date, 'charge'
    FROM charging_processes cp
    WHERE cp.car_id IN (SELECT id FROM scope_cars)
        AND (%(days)s::int IS NULL OR cp.start_date >= CURRENT_DATE - make_interval(days => %(days)s))
),
located AS (
    SELECT a.country,
        CASE WHEN %(level)s::text IN ('state', 'city') THEN a.state END AS state,
        CASE WHEN %(level)s::text = 'city' THEN a.city END AS city,
        v.address_id,
        v.at,
        v.kind
    FROM visits v
        JOIN addresses a ON a.id = v.address_id
)
SELECT country,
    state,
    city,
    COUNT(DISTINCT address_id) AS places,
    COUNT(*) FILTER (WHERE kind = 'arrival') AS arrivals,
    COUNT(*) FILTER (WHERE kind = 'charge') AS charging_sessions,
    TO_CHAR(((MIN(at) AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date, 'YYYY-MM-DD')
        AS first_visit,
    TO_CHAR(((MAX(at) AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date, 'YYYY-MM-DD')
        AS last_visit
FROM located
GROUP BY country, state, city
ORDER BY arrivals DESC, charging_sessions DESC, country, state, city
LIMIT %(limit)s::int;
