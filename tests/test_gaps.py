"""Car status climate and tires, session header, geo-fence directory, logging gaps."""

from __future__ import annotations


async def _rows(session, tool: str, **args) -> list[dict]:
    result = await session.call_tool(tool, args)
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_car_status_takes_climate_and_tires_from_latest_non_null_rows(
    mcp_session,
) -> None:
    async with mcp_session(seeds=["status"]) as session:
        poller = (await _rows(session, "get_current_car_status", car_name="poller"))[0]
        blue = (await _rows(session, "get_current_car_status", car_name="blue"))[0]

    # The latest row is an in-drive sample with neither group.
    assert (poller["battery_level"], poller["odometer"]) == (70, 2130.0)
    assert poller["inside_temp"] == 22.5
    assert (poller["driver_temp_setting"], poller["passenger_temp_setting"]) == (21.0, 20.5)
    assert poller["fan_status"] == 3
    assert (poller["is_front_defroster_on"], poller["is_rear_defroster_on"]) == (False, True)
    assert (
        poller["tpms_pressure_fl"],
        poller["tpms_pressure_fr"],
        poller["tpms_pressure_rl"],
        poller["tpms_pressure_rr"],
    ) == (2.9, 3.0, 2.8, 2.9)
    assert poller["climate_at"] < poller["tpms_at"] < poller["last_update"]

    # No climate row at all; tires on the latest row itself.
    assert blue["inside_temp"] is None
    assert blue["climate_at"] is None
    assert (blue["tpms_pressure_fl"], blue["tpms_pressure_fr"]) == (2.9, 3.0)
    assert blue["tpms_at"] == blue["last_update"]


async def test_drive_details_include_ideal_range_and_geofence(mcp_session) -> None:
    async with mcp_session() as session:
        row = (await _rows(session, "get_drive_details", drive_id=4))[0]

    assert (row["start_ideal_range_km"], row["end_ideal_range_km"]) == (510.0, 480.0)
    assert row["ideal_range_used_km"] == 30.0
    assert row["start_geofence"] == "Home"
    assert row["end_geofence"] is None


async def test_charging_session_header_covers_ac_and_dc(mcp_session) -> None:
    async with mcp_session() as session:
        ac = (await _rows(session, "get_charging_session", charging_process_id=1))[0]
        dc = (await _rows(session, "get_charging_session", charging_process_id=2))[0]

    assert ac["charger_kind"] == "ac"
    assert ac["phases"] == 1
    assert ac["cable"] == "IEC"
    assert (ac["energy_added_kwh"], ac["energy_used_kwh"]) == (30.0, 33.0)
    assert (ac["start_soc"], ac["end_soc"]) == (40, 80)
    assert ac["cost"] == 12.5
    assert ac["geofence_name"] == "Home"
    assert ac["peak_power_kw"] == 11

    assert dc["charger_kind"] == "other_dc"
    assert dc["phases"] is None
    assert (dc["energy_added_kwh"], dc["energy_used_kwh"]) == (50.0, 54.0)
    assert dc["geofence_name"] is None
    assert dc["location"] == "Supercharger Edirne"
    assert dc["cost"] == 30.0


async def test_geofence_directory_lists_tariffs(mcp_session) -> None:
    async with mcp_session() as session:
        rows = await _rows(session, "get_geofences")

    by_name = {row["name"]: row for row in rows}
    assert by_name["Home"]["billing_type"] == "per_kwh"
    assert by_name["Home"]["cost_per_unit"] == 0.28
    assert by_name["Home"]["radius_m"] == 25
    assert by_name["Home"]["session_fee"] is None
    assert by_name["Depot"]["billing_type"] == "per_minute"
    assert by_name["Depot"]["session_fee"] == 1.5
    assert by_name["Depot"]["radius_m"] == 300


async def test_logging_gaps_keep_only_holes_that_hide_a_drive_or_charge(mcp_session) -> None:
    async with mcp_session(seeds=["gaps"]) as session:
        day = await _rows(session, "get_logging_gaps", car_name="gapper")
        fine = await _rows(session, "get_logging_gaps", car_name="gapper", min_hours=1)

    kinds = [row["gap_kind"] for row in day]
    assert kinds.count("open_drive") == 1
    assert "open_charge" not in kinds
    open_drive = next(row for row in day if row["gap_kind"] == "open_drive")
    assert open_drive["record_id"] is not None
    assert open_drive["ended_at"] is None
    assert open_drive["odometer_change_km"] is None
    # The seed and the query both use UTC, so the session time zone of the
    # database does not move this. A UTC+3 server gave 69 h with a local seed.
    assert 72.0 <= open_drive["duration_hours"] < 72.5

    # The 96 h and 69 h parked holes stay out: no odometer change, no rise.
    holes = [row for row in day if row["gap_kind"] == "position_hole"]
    assert [row["duration_hours"] for row in holes] == [72.0]
    assert (holes[0]["odometer_change_km"], holes[0]["battery_change"]) == (100.0, -10)
    assert holes[0]["record_id"] is None

    fine_kinds = [row["gap_kind"] for row in fine]
    assert fine_kinds.count("open_charge") == 1
    fine_holes = [row for row in fine if row["gap_kind"] == "position_hole"]
    assert [row["duration_hours"] for row in fine_holes] == [72.0, 2.0]
    assert (fine_holes[1]["odometer_change_km"], fine_holes[1]["battery_change"]) == (0.0, 20)
