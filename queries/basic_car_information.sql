SELECT c.name,
    c.model,
    c.trim_badging,
    c.exterior_color,
    c.marketing_name,
    cs.enabled,
    cs.free_supercharging
FROM cars c
    LEFT JOIN car_settings cs ON c.settings_id = cs.id;