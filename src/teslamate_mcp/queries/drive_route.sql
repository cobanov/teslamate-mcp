WITH route AS (
    SELECT p.date,
        p.latitude,
        p.longitude,
        p.battery_level,
        p.speed,
        p.power,
        p.odometer,
        NTILE(%(max_points)s::int) OVER (ORDER BY p.date) AS bucket
    FROM drives d
        JOIN positions p ON p.car_id = d.car_id
            AND p.date BETWEEN d.start_date AND d.end_date
    WHERE d.id = %(drive_id)s::int
        AND p.latitude IS NOT NULL
        AND p.longitude IS NOT NULL
)
SELECT bucket AS point_order,
    MIN(date) AS ts,
    ROUND(AVG(latitude)::numeric, 6) AS latitude,
    ROUND(AVG(longitude)::numeric, 6) AS longitude,
    MIN(battery_level) AS battery_level,
    MAX(speed) AS speed_max_kmh,
    ROUND(AVG(power)::numeric, 1) AS avg_power_kw,
    MAX(odometer) AS odometer_km
FROM route
GROUP BY bucket
ORDER BY point_order;
