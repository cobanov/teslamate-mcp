"""MCP prompts: pre-baked instructions for common TeslaMate analyses.

Each prompt returns a multi-step instruction string that names the specific
tools the client should call and the order in which to call them. This keeps
the language model from re-deriving the workflow every time and gives users
a single-click entry point in MCP-aware UIs.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer


def register_prompts(mcp: MCPServer) -> None:
    """Attach the prompt catalog to the server."""

    @mcp.prompt(
        name="analyze_battery_health",
        description="Comprehensive battery health and degradation analysis.",
    )
    async def analyze_battery_health() -> str:
        return (
            "Analyze the battery health of this Tesla:\n"
            "1. Call `get_battery_capacity_trend` for usable capacity in kWh over "
            "time, measured from charging sessions (the most direct signal).\n"
            "2. Call `get_battery_health_summary` and `show_battery_degradation` "
            "for the rated-range view of the same trend.\n"
            "3. Call `get_basic_car_information` for the model, age, and odometer.\n"
            "4. Call `get_soc_hygiene` (time spent above 80% and below 20%) and "
            "`get_fast_charging_sessions` (how often it DC fast-charges).\n"
            "5. Compare the capacity loss with what is typical for this model and "
            "age, flag any deviation, and relate it to the charging habits found. "
            "Recommend concrete next steps only where the data supports them."
        )

    @mcp.prompt(
        name="summarize_driving",
        description="Summarize driving habits and totals over a chosen window.",
    )
    async def summarize_driving(window: str = "last 30 days") -> str:
        return (
            f"Summarize driving habits for the {window}:\n"
            "1. Call `get_monthly_driving_summary` and `get_drive_summary_per_day` "
            "for totals — pass a `days` argument matching the requested window "
            "(e.g. days=30).\n"
            "2. Call `get_daily_driving_patterns` (same `days`) to identify usage "
            "peaks by day of week.\n"
            "3. Call `get_trips` for the journeys in the window (a journey with "
            "stops is several drives in TeslaMate), or `search_drives` for single "
            "drives.\n"
            "4. Produce a short report: total distance, average drive length, "
            "peak day, most-used time slot, the longest journeys, and any notable "
            "outliers."
        )

    @mcp.prompt(
        name="analyze_charging",
        description="Charging patterns, locations, and efficiency breakdown.",
    )
    async def analyze_charging() -> str:
        return (
            "Build a complete picture of charging behavior:\n"
            "1. Call `get_all_charging_sessions_summary` for the totals and "
            "`get_charging_efficiency` for AC vs DC losses.\n"
            "2. Call `get_charging_by_location` to see where charging happens and "
            "`get_fast_charging_by_location` for how fast each fast charger was.\n"
            "3. Call `get_charging_costs` with group_by='month' and again with "
            "group_by='location'. If sessions_without_cost is not zero, call "
            "`get_charging_cost_estimates` so the totals are not understated.\n"
            "4. Highlight: home-vs-public split, kWh added per location, cost per "
            "kWh trends, and any session that looks unusually slow or expensive. "
            "For suspicious sessions, call `show_charging_curve_comparison` with "
            "their charging_process_ids next to a normal one."
        )

    @mcp.prompt(
        name="find_anomalies",
        description="Surface unusual power consumption or driving anomalies.",
    )
    async def find_anomalies() -> str:
        return (
            "Look for anomalies in the recorded data:\n"
            "1. Call `get_unusual_power_consumption` to fetch flagged events.\n"
            "2. Call `get_efficiency_by_month_and_temperature` and "
            "`get_average_efficiency_by_temperature` to see whether the "
            "anomalies correlate with weather.\n"
            "3. Call `get_tire_pressure_weekly_trends` — low pressure often "
            "shows up as efficiency loss — and `get_efficiency_by_elevation` for "
            "hilly routes.\n"
            "4. Call `get_idle_awake_periods` and `get_vampire_drain` for battery "
            "lost while parked.\n"
            "5. For each anomaly, propose a likely cause (cold weather, climbing, "
            "hard driving, a car that does not sleep, tire pressure) and what to "
            "check next."
        )

    @mcp.prompt(
        name="weather_efficiency",
        description="Quantify how temperature affects the vehicle's efficiency.",
    )
    async def weather_efficiency() -> str:
        return (
            "Quantify the temperature impact on efficiency:\n"
            "1. Call `show_efficiency_vs_temperature` to plot every drive, and "
            "`get_average_efficiency_by_temperature` for the grouped numbers.\n"
            "2. Call `get_efficiency_by_month_and_temperature` for the seasonal "
            "view.\n"
            "3. Compare warm-weather (>20°C) vs cold-weather (<5°C) Wh/km.\n"
            "4. Translate the delta into expected range loss in winter, and "
            "give one or two practical tips for cold-weather range."
        )

    @mcp.prompt(
        name="status_report",
        description="Quick one-screen status snapshot for the current vehicle.",
    )
    async def status_report() -> str:
        return (
            "Produce a quick status snapshot:\n"
            "1. Call `get_current_car_status` for what the car is doing (driving, "
            "charging, online, asleep), where it is, and its battery level.\n"
            "2. Call `get_basic_car_information` for model and trim.\n"
            "3. Call `get_software_update_history` for the installed firmware and "
            "when it arrived. TeslaMate does not record whether an update is "
            "waiting, so do not claim one is or is not.\n"
            "4. Present a single short paragraph: what the car is doing and since "
            "when, where it is, battery level, climate state, and firmware. If "
            "last_update is old, say that TeslaMate has lost contact with the car."
        )

    @mcp.prompt(
        name="diagnose_sleep",
        description="Find out why the car is not sleeping or loses battery while parked.",
    )
    async def diagnose_sleep(days: str = "14") -> str:
        return (
            f"Find out whether the car sleeps properly over the last {days} days:\n"
            f"1. Call `get_state_history` with days={days} for hours asleep, "
            "offline, and online per day, and the idle awake hours.\n"
            "2. Call `get_idle_awake_periods` for when and where it stayed awake "
            "while parked.\n"
            "3. Call `get_vampire_drain` for the range lost while parked.\n"
            "4. Explain the pattern: healthy cars are asleep or offline most of a "
            "parked day. Relate long awake periods to their time and place and "
            "suggest likely causes (Sentry Mode, cabin overheat protection, "
            "climate left on, third-party apps polling the car, scheduled "
            "charging) with what to check first."
        )

    @mcp.prompt(
        name="plan_trip",
        description="Check whether a drive is possible on the current charge, from the car's own history.",
    )
    async def plan_trip(destination: str, outside_temp_c: str = "") -> str:
        temp = (
            f"The expected outside temperature is {outside_temp_c} °C."
            if outside_temp_c
            else "Use a weather forecast for the expected outside temperature if one is available."
        )
        return (
            f"Plan a drive to {destination}. {temp}\n"
            "1. Get the driving distance from a maps or routing tool; ask the user "
            "for it if none is available.\n"
            "2. Call `get_trip_energy_estimate` with distance_km and outside_temp_c, "
            "and highway=true for a motorway route.\n"
            "3. For a hilly route, call `get_efficiency_by_elevation` and adjust "
            "the estimate by the uphill or downhill difference.\n"
            "4. If the conservative arrival battery % is below about 10%, suggest "
            "where to charge: `get_fast_charging_by_location` shows fast chargers "
            "the car has used and how fast they were.\n"
            "5. Answer plainly: expected and conservative arrival %, whether a "
            "stop is needed, and how much margin is left."
        )

    @mcp.prompt(
        name="review_trip",
        description="Walk through one road trip: legs, stops, charging, and energy.",
    )
    async def review_trip(which: str = "the latest trip") -> str:
        return (
            f"Review {which}:\n"
            "1. Call `get_trips` (filter by date or location to find it) and pick "
            "the trip.\n"
            "2. Call `get_trip_details` with its trip_id for every leg and stop.\n"
            "3. Call `show_trip_route` with the trip_id to show the route, its "
            "stops, and the elevation profile.\n"
            "4. Summarize: distance, driving vs stopped time, each charging stop "
            "(where, how long, kWh), battery % at start and end, average speed, "
            "and the climb. For a slow charging stop, call "
            "`show_charging_curve_comparison` with its charging_process_id."
        )

    @mcp.prompt(
        name="monthly_recap",
        description="A recap of one month: driving, charging, costs, and places.",
    )
    async def monthly_recap(month: str = "this month") -> str:
        return (
            f"Recap {month}:\n"
            "1. Call `show_recap` with period='month' and the year and month meant "
            "(leave them out for the current month) for the totals, the change "
            "against the month before, and the highlights.\n"
            "2. Call `get_activity_report` with the same period for the day-by-day "
            "picture behind them.\n"
            "3. Call `get_climate_usage` with months=1 (more for a past month) for "
            "the climate run while parked.\n"
            "4. Write a short recap: distance and drives and how that compares, "
            "consumption and what drove it (temperature, trips, climate), energy "
            "charged and cost, the busiest day, the longest drive, and the places "
            "visited most."
        )

    @mcp.prompt(
        name="year_in_review",
        description="A year in review ('Wrapped'): totals, highlights, and records.",
    )
    async def year_in_review(year: str = "this year") -> str:
        return (
            f"Review {year}:\n"
            "1. Call `show_recap` with period='year' and the year meant (leave it "
            "out for the current year) for the totals, the change against the "
            "year before, and the highlights.\n"
            "2. Call `get_activity_report` with period='year' for the month by "
            "month picture: the busiest and quietest months, and how consumption "
            "followed the seasons.\n"
            "3. Call `get_climate_usage` with months=12 for the climate run while "
            "parked.\n"
            "4. Write it like a year-end wrap-up: the headline distance and how it "
            "compares, the longest drive and where it went, the favourite "
            "destination and charging spot, the most efficient month, the "
            "temperature extremes, and what charging cost. If the year is still "
            "running, say so."
        )

    @mcp.prompt(
        name="charging_costs_and_savings",
        description="What charging cost, filling in missing costs, compared with a petrol car.",
    )
    async def charging_costs_and_savings(
        fuel_price_per_liter: str = "", fuel_consumption_l_per_100km: str = "7"
    ) -> str:
        price = (
            f"Use a fuel price of {fuel_price_per_liter} per liter"
            if fuel_price_per_liter
            else "Ask the user for their local fuel price per liter"
        )
        return (
            "Work out what charging has cost and what it saved:\n"
            "1. Call `get_charging_costs` with group_by='month'. Where "
            "sessions_without_cost is not zero, call `get_charging_cost_estimates` "
            "and say how much of the total is estimated.\n"
            f"2. {price} and a comparison car using {fuel_consumption_l_per_100km} "
            "L/100 km, then call `get_fuel_savings` with them. If cost_coverage_pct "
            "is below 100, pass electricity_price_per_kwh (the typical home price "
            "from step 1).\n"
            "3. Report cost per 100 km electric vs fuel, total savings, and the "
            "most and least expensive places to charge."
        )
