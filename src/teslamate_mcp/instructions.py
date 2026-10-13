"""Server instructions: how to read the data and which tool answers what.

Clients hand these to the model once per connection. With close to sixty
tools, a short map from question to tool keeps the model from reaching for
run_sql or the wrong granularity (drives vs trips), and the unit and time
notes keep it from misreading the numbers.
"""

from __future__ import annotations

from .config import Settings


def build_instructions(settings: Settings) -> str:
    """The instructions for this server, reflecting its configuration."""
    lines = [
        "Read-only access to a TeslaMate database: the driving, charging, battery, and "
        "state history of one or more Teslas.",
        "",
        "Reading the numbers:",
        "- Values are metric (km, km/h, °C, bar, m, kWh, Wh/km) and ranges are rated "
        "range. Call `get_unit_preferences` once and answer in the units the user set "
        "in TeslaMate (miles, °F, psi).",
        "- Timestamps are UTC. Columns ending in _local, day and month buckets, and "
        f"date filters use the local time zone {settings.report_timezone}.",
        "- Costs are in the currency the user set in TeslaMate. A session with no cost "
        "is unknown, not free.",
        "- car_name filters by case-insensitive substring; leave it out for all cars "
        "and say which car each number belongs to.",
        "",
        "Which tool:",
        "- Where is the car, is it charging or asleep: `get_current_car_status`. What "
        "it did on a day or week: `get_timeline`.",
        "- Journeys: `get_trips` (TeslaMate ends a drive at every stop, so a journey "
        "is several drives). Single drives: `search_drives`, `get_drive_details`.",
        "- Not sleeping, battery lost while parked: `get_state_history`, "
        "`get_idle_awake_periods`, `get_vampire_drain`.",
        "- Can I make it: `get_trip_energy_estimate` (take the distance from a maps "
        "tool); hills: `get_efficiency_by_elevation`.",
        "- Battery health: `get_battery_capacity_trend` (energy-based) first, then "
        "`get_battery_degradation_over_time`.",
        "- Charging: `search_charging_sessions`, `get_fast_charging_sessions`, "
        "`get_fast_charging_by_location`. Money: `get_charging_costs`, "
        "`get_charging_cost_estimates`, `get_fuel_savings`.",
        "- Overviews: `get_activity_report` (a month or year), `get_period_comparison`.",
        "- Anything else: `get_database_schema`, then a read-only `run_sql`.",
        "",
        "Charts: each show_* tool draws an interactive chart on clients that support "
        "MCP Apps and returns the same rows as its get_* twin, so call one or the "
        "other, not both. Prefer show_* when the user wants to see something. Charts "
        "use metric units.",
        "",
        "Ids: drive_id, trip_id (a trip's first drive id), and charging_process_id "
        "come from the search, list, and timeline tools.",
    ]
    if settings.enable_charging_writes:
        lines += [
            "",
            "Cost writes are enabled: `set_charging_cost` stores one session's cost. "
            "Propose values from receipts or `get_charging_cost_estimates` and write "
            "only what the user confirmed.",
        ]
    return "\n".join(lines)
