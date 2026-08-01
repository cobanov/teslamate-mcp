WITH curve AS (
    SELECT date,
        battery_level,
        charger_power,
        charger_voltage,
        charger_actual_current,
        rated_battery_range_km,
        outside_temp,
        NTILE(%(max_points)s::int) OVER (ORDER BY date) AS bucket
    FROM charges
    WHERE charging_process_id = %(charging_process_id)s::int
)
SELECT MIN(date) AS bucket_start,
    MIN(battery_level) AS battery_level_start,
    MAX(battery_level) AS battery_level_end,
    ROUND(AVG(charger_power)::numeric, 1) AS avg_power_kw,
    MAX(charger_power) AS max_power_kw,
    ROUND(AVG(charger_voltage)::numeric, 0) AS avg_voltage,
    ROUND(AVG(charger_actual_current)::numeric, 1) AS avg_current_a,
    ROUND(AVG(rated_battery_range_km)::numeric, 1) AS avg_rated_range_km,
    ROUND(AVG(outside_temp)::numeric, 1) AS avg_outside_temp
FROM curve
GROUP BY bucket
ORDER BY bucket_start;
