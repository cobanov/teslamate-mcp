"""Tool definitions for TeslaMate MCP server"""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ToolDefinition:
    """Definition of a TeslaMate tool"""

    name: str
    description: str
    sql_file: str


# All TeslaMate tools with their definitions
TOOL_DEFINITIONS = [
    ToolDefinition(
        name="get_all_charging_sessions_summary",
        description="Get the summary of all charging sessions for each car. Returns charging statistics including total sessions, energy consumed, and costs.",
        sql_file="all_charging_sessions_summary.sql",
    ),
    ToolDefinition(
        name="get_average_efficiency_by_temperature",
        description="Get the average efficiency by temperature for each car. Helps understand how temperature affects vehicle efficiency.",
        sql_file="average_efficiency_by_temperature.sql",
    ),
    ToolDefinition(
        name="get_basic_car_information",
        description="Get the basic car information for each car. Returns VIN, model, firmware version, and other vehicle details.",
        sql_file="basic_car_information.sql",
    ),
    ToolDefinition(
        name="get_battery_degradation_over_time",
        description="Get the battery degradation over time for each car. Tracks battery health metrics and capacity changes.",
        sql_file="battery_degradation_over_time.sql",
    ),
    ToolDefinition(
        name="get_battery_health_summary",
        description="Get the battery health summary for each car. Provides current battery health status and statistics.",
        sql_file="battery_health_summary.sql",
    ),
    ToolDefinition(
        name="get_charging_by_location",
        description="Get the charging by location for each car. Shows charging patterns and statistics grouped by location.",
        sql_file="charging_by_location.sql",
    ),
    ToolDefinition(
        name="get_current_car_status",
        description="Get the current car status for each car. Returns real-time vehicle status including location, battery level, and state.",
        sql_file="current_car_status.sql",
    ),
    ToolDefinition(
        name="get_daily_battery_usage_patterns",
        description="Get the daily battery usage patterns for each car. Analyzes battery consumption patterns throughout the day.",
        sql_file="daily_battery_usage.sql",
    ),
    ToolDefinition(
        name="get_daily_driving_patterns",
        description="Get the daily driving patterns for each car. Shows driving habits and patterns by day of week and time.",
        sql_file="daily_driving_patterns.sql",
    ),
    ToolDefinition(
        name="get_drive_summary_per_day",
        description="Get the drive summary per day for each car. Provides daily driving statistics including distance, duration, and efficiency.",
        sql_file="drive_summary_per_day.sql",
    ),
    ToolDefinition(
        name="get_efficiency_by_month_and_temperature",
        description="Get the efficiency by month and temperature for each car. Analyzes how seasonal temperature changes affect vehicle efficiency.",
        sql_file="efficiency_by_month_and_temperature.sql",
    ),
    ToolDefinition(
        name="get_longest_drives_by_distance",
        description="Get the longest drives by distance for each car. Lists the longest trips taken with details about distance and duration.",
        sql_file="longest_drives_by_distance.sql",
    ),
    ToolDefinition(
        name="get_monthly_driving_summary",
        description="Get the monthly driving summary for each car. Provides monthly statistics for distance, energy usage, and costs.",
        sql_file="monthly_driving_summary.sql",
    ),
    ToolDefinition(
        name="get_most_visited_locations",
        description="Get the most visited locations for each car. Shows frequently visited places with visit counts and durations.",
        sql_file="most_visited_locations.sql",
    ),
    ToolDefinition(
        name="get_software_update_history",
        description="Get the software update history for each car. Tracks firmware updates and version changes over time.",
        sql_file="software_update_history.sql",
    ),
    ToolDefinition(
        name="get_tire_pressure_weekly_trends",
        description="Get the tire pressure weekly trends for each car. Monitors tire pressure changes and patterns by week.",
        sql_file="tire_pressure_weekly_trend.sql",
    ),
    ToolDefinition(
        name="get_total_distance_and_efficiency",
        description="Get the total distance and efficiency for each car. Provides lifetime statistics for distance traveled and energy efficiency.",
        sql_file="total_distance_and_efficiency.sql",
    ),
    ToolDefinition(
        name="get_unusual_power_consumption",
        description="Get the unusual power consumption for each car. Identifies anomalies in power usage that might indicate issues.",
        sql_file="unusual_power_consumption.sql",
    ),
]


def get_tool_by_name(name: str) -> ToolDefinition:
    """Get a tool definition by name"""
    for tool in TOOL_DEFINITIONS:
        if tool.name == name:
            return tool
    raise ValueError(f"Unknown tool: {name}")


def get_all_tool_names() -> List[str]:
    """Get all tool names"""
    return [tool.name for tool in TOOL_DEFINITIONS]

