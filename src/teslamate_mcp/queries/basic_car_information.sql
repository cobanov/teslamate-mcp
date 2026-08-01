SELECT c.name,
    c.model,
    c.trim_badging,
    c.exterior_color,
    c.marketing_name,
    cs.enabled,
    cs.free_supercharging
FROM cars c
    LEFT JOIN car_settings cs ON c.settings_id = cs.id
WHERE (%(car_name)s::text IS NULL OR c.name ILIKE '%%' || %(car_name)s || '%%');