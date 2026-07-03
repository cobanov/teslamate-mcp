SELECT cp.id AS charging_process_id,
    c.name AS car_name,
    cp.start_date,
    cp.end_date,
    cp.charge_energy_added AS energy_added_kwh,
    cp.duration_min,
    cp.cost,
    a.display_name AS location,
    a.city
FROM charging_processes cp
    JOIN cars c ON cp.car_id = c.id
    LEFT JOIN addresses a ON cp.address_id = a.id
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%')
    AND (%(start_date)s::date IS NULL
        OR ((cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date >= %(start_date)s::date)
    AND (%(end_date)s::date IS NULL
        OR ((cp.start_date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s::text)::date <= %(end_date)s::date)
    AND (%(location)s::text IS NULL
        OR a.display_name ILIKE '%%' || %(location)s || '%%'
        OR a.city ILIKE '%%' || %(location)s || '%%')
    AND (%(min_energy_kwh)s::float8 IS NULL OR cp.charge_energy_added >= %(min_energy_kwh)s)
ORDER BY cp.start_date DESC
LIMIT %(limit)s::int;
