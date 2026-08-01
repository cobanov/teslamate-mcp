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
            "1. Call `get_battery_health_summary` for the current state of health.\n"
            "2. Call `get_battery_degradation_over_time` to see the historical "
            "capacity curve.\n"
            "3. Call `get_basic_car_information` to know the model, original "
            "rated range, and total odometer.\n"
            "4. Estimate expected degradation for this model/age and flag any "
            "deviation. Recommend next steps if degradation is faster than "
            "typical (e.g. avoid frequent supercharging, keep SoC between "
            "20-80%)."
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
            "3. Call `get_longest_drives_by_distance` for the standout trips, or "
            "`search_drives` with a date range for a specific period.\n"
            "4. Produce a short report: total distance, average drive length, "
            "peak day, most-used time slot, and any notable outliers."
        )

    @mcp.prompt(
        name="analyze_charging",
        description="Charging patterns, locations, and efficiency breakdown.",
    )
    async def analyze_charging() -> str:
        return (
            "Build a complete picture of charging behavior:\n"
            "1. Call `get_all_charging_sessions_summary` for the totals.\n"
            "2. Call `get_charging_by_location` to see where charging happens.\n"
            "3. Call `get_charging_costs` with group_by='month' and again with "
            "group_by='location' for the cost breakdown.\n"
            "4. Highlight: home-vs-public split, kWh added per location, cost "
            "per kWh trends, and any session that looks unusually slow or "
            "expensive — for a suspicious session, call `get_charging_curve` "
            "with its charging_process_id to inspect the power curve."
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
            "shows up as efficiency loss.\n"
            "4. For each anomaly, propose a likely cause (cold weather, hard "
            "driving, vampire drain, tire pressure) and what to check next."
        )

    @mcp.prompt(
        name="weather_efficiency",
        description="Quantify how temperature affects the vehicle's efficiency.",
    )
    async def weather_efficiency() -> str:
        return (
            "Quantify the temperature impact on efficiency:\n"
            "1. Call `get_average_efficiency_by_temperature`.\n"
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
            "1. Call `get_current_car_status` for live state, location, and "
            "battery level.\n"
            "2. Call `get_basic_car_information` for VIN, model, and firmware.\n"
            "3. Call `get_software_update_history` to check whether the car is "
            "on the latest firmware.\n"
            "4. Present a single short paragraph: where the car is, battery "
            "level, climate state, current firmware, and any pending update."
        )
