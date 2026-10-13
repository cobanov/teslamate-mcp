"""get_timeline: drives, charges, parks, and updates in order."""

from __future__ import annotations

_CAR = "Road Tripper"


async def _rows(session, tool: str, **args) -> list[dict]:
    result = await session.call_tool(tool, args)
    assert not result.is_error, [getattr(c, "text", c) for c in result.content]
    return result.structured_content["result"]


async def test_timeline_orders_drives_charges_and_parks(mcp_session) -> None:
    async with mcp_session(with_trips=True) as session:
        rows = await _rows(
            session, "get_timeline", car_name=_CAR, start_date="2025-06-10", end_date="2025-06-10"
        )

    assert [r["activity"] for r in rows] == [
        "drive",
        "park",  # 20-min WC stop
        "drive",
        "park",  # 5 min from arrival to plugging in
        "charge",
        "park",
        "drive",
        "park",  # afternoon in Ankara
        "charge",  # the overnight hotel charge, which starts on this day
    ]
    first_drive, wc_stop = rows[0], rows[1]
    assert (first_drive["location"], first_drive["destination"]) == (
        "Home Street 1",
        "Bolu Rest Area",
    )
    assert first_drive["distance_km"] == 140.0
    assert (first_drive["battery_start"], first_drive["battery_end"]) == (90, 68)
    assert first_drive["drive_id"] == 101
    assert (wc_stop["location"], wc_stop["duration_min"]) == ("Bolu Rest Area", 20)
    assert (wc_stop["battery_start"], wc_stop["battery_end"]) == (68, 68)
    assert wc_stop["pct_asleep_or_offline"] is None  # no state log for this car

    supercharge = rows[4]
    assert supercharge["charging_process_id"] == 101
    assert supercharge["energy_added_kwh"] == 35.0
    assert (supercharge["battery_start"], supercharge["battery_end"]) == (30, 75)
    after_charge = rows[5]
    assert after_charge["location"] == "Supercharger Bolu"
    assert (after_charge["battery_start"], after_charge["battery_end"]) == (75, 84)
    assert (rows[7]["location"], rows[7]["duration_min"]) == ("Kizilay Square", 520)
    assert rows[8]["end_local"] == "2025-06-11 06:00"


async def test_timeline_min_park_and_limit(mcp_session) -> None:
    window = {"car_name": _CAR, "start_date": "2025-06-10", "end_date": "2025-06-10"}
    async with mcp_session(with_trips=True) as session:
        longer_parks = await _rows(session, "get_timeline", min_park_minutes=10, **window)
        newest = await _rows(session, "get_timeline", limit=3, **window)

    assert len(longer_parks) == 8  # the 5-min park before the charge is gone
    # The limit keeps the newest rows, still in chronological order.
    assert [(r["activity"], r["start_local"]) for r in newest] == [
        ("drive", "2025-06-10 09:50"),
        ("park", "2025-06-10 11:20"),
        ("charge", "2025-06-10 20:00"),
    ]


async def test_timeline_park_sleep_share_and_ongoing_park(mcp_session) -> None:
    async with mcp_session(seeds=["states"]) as session:
        rows = await _rows(session, "get_timeline", car_name="night owl")

    # The orphaned open drive is not an activity.
    assert [r["activity"] for r in rows] == ["drive", "park", "charge", "park"]
    between, parked_now = rows[1], rows[3]
    assert between["pct_asleep_or_offline"] == 0  # the car stayed online
    assert parked_now["end_date"] is None  # parked ever since
    assert parked_now["location"] == "Office Plaza"
    assert parked_now["pct_asleep_or_offline"] >= 96  # 30 min online, then offline/asleep


async def test_timeline_includes_software_updates(mcp_session) -> None:
    async with mcp_session() as session:
        rows = await _rows(session, "get_timeline", car_name="blue")

    updates = [r for r in rows if r["activity"] == "update"]
    assert [u["version"] for u in updates] == ["2026.20.1"]


async def test_timeline_local_times_follow_report_timezone(mcp_session) -> None:
    async with mcp_session(with_trips=True, report_timezone="Europe/Istanbul") as session:
        rows = await _rows(
            session, "get_timeline", car_name=_CAR, start_date="2025-06-11", end_date="2025-06-11"
        )

    # 06:00 UTC is 09:00 in Istanbul; the hotel charge began at 23:00 local on
    # the 10th and is still in the window because it ran into the 11th.
    assert rows[0]["activity"] == "charge"
    assert (rows[0]["start_local"], rows[0]["end_local"]) == (
        "2025-06-10 23:00",
        "2025-06-11 09:00",
    )
