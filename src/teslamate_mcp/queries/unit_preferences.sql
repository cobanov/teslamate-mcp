-- TeslaMate's display preferences (its Settings page). Every tool returns
-- metric values (km, km/h, °C, bar, m) and rated range whatever these say;
-- they tell the assistant what to convert to when presenting. Read through
-- to_jsonb so an older TeslaMate without one of the columns still answers,
-- and fall back to TeslaMate's defaults when there is no settings row.
SELECT COALESCE(s.prefs ->> 'unit_of_length', 'km') AS unit_of_length,
    COALESCE(s.prefs ->> 'unit_of_temperature', 'C') AS unit_of_temperature,
    COALESCE(s.prefs ->> 'unit_of_pressure', 'bar') AS unit_of_pressure,
    COALESCE(s.prefs ->> 'preferred_range', 'rated') AS preferred_range,
    s.prefs ->> 'language' AS language
FROM (SELECT 1) AS one
    LEFT JOIN LATERAL (
        SELECT to_jsonb(st) AS prefs
        FROM settings st
        ORDER BY st.id
        LIMIT 1
    ) s ON TRUE;
