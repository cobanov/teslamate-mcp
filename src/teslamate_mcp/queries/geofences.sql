-- The geo-fence directory. Charging totals by fence are a different tool.
SELECT g.id AS geofence_id,
    g.name,
    g.latitude,
    g.longitude,
    g.radius AS radius_m,
    g.cost_per_unit,
    g.session_fee,
    g.billing_type::text AS billing_type
FROM geofences g
ORDER BY g.name, g.id;
