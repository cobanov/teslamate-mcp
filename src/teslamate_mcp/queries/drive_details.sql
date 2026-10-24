SELECT d.id AS drive_id,
    c.name AS car_name,
    d.start_date,
    d.end_date,
    d.distance AS distance_km,
    d.duration_min,
    ROUND((d.distance / NULLIF(d.duration_min, 0) * 60)::numeric, 1) AS avg_speed_kmh,
    d.speed_max,
    d.power_max,
    d.power_min,
    d.inside_temp_avg,
    d.outside_temp_avg,
    d.ascent AS ascent_m,
    d.descent AS descent_m,
    d.start_km AS odometer_start_km,
    d.end_km AS odometer_end_km,
    d.start_rated_range_km,
    d.end_rated_range_km,
    (d.start_rated_range_km - d.end_rated_range_km) AS rated_range_used_km,
    d.start_ideal_range_km,
    d.end_ideal_range_km,
    (d.start_ideal_range_km - d.end_ideal_range_km) AS ideal_range_used_km,
    ROUND(
        ((d.start_rated_range_km - d.end_rated_range_km) / NULLIF(d.distance, 0) * 100)::numeric,
        1
    ) AS consumption_pct,
    start_addr.display_name AS start_location,
    start_addr.city AS start_city,
    end_addr.display_name AS end_location,
    end_addr.city AS end_city,
    start_fence.name AS start_geofence,
    end_fence.name AS end_geofence,
    ROUND(e.used_kwh::numeric, 2) AS energy_used_kwh,
    ROUND(e.recovered_kwh::numeric, 2) AS energy_recovered_kwh,
    ROUND((100 * e.recovered_kwh / NULLIF(e.used_kwh, 0))::numeric, 1) AS regen_share_pct
FROM drives d
    JOIN cars c ON d.car_id = c.id
    LEFT JOIN addresses start_addr ON d.start_address_id = start_addr.id
    LEFT JOIN addresses end_addr ON d.end_address_id = end_addr.id
    LEFT JOIN geofences start_fence ON d.start_geofence_id = start_fence.id
    LEFT JOIN geofences end_fence ON d.end_geofence_id = end_fence.id
    -- Energy at the battery from the power samples: each sample stands for the
    -- time until the next one, and gaps over a minute are logging holes.
    -- Positive power drives the car, negative power is regenerative braking.
    LEFT JOIN LATERAL (
        SELECT SUM(s.power * s.dt) FILTER (WHERE s.power > 0) / 3600 AS used_kwh,
            -SUM(s.power * s.dt) FILTER (WHERE s.power < 0) / 3600 AS recovered_kwh
        FROM (
            SELECT p.power,
                EXTRACT(EPOCH FROM (LEAD(p.date) OVER (ORDER BY p.date) - p.date))::float8 AS dt
            FROM positions p
            WHERE p.drive_id = d.id
                AND p.power IS NOT NULL
        ) s
        WHERE s.dt > 0
            AND s.dt <= 60
    ) e ON TRUE
WHERE d.id = %(drive_id)s::int;
