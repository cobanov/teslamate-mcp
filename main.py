import logging
import os
from typing import Any, List, Tuple

import psycopg
from psycopg.rows import dict_row

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("teslamate")
con_str = os.getenv("DATABASE_URL")


def read_from_sql_file(file_path: str) -> str:
    with open(file_path, "r") as file:
        return file.read()


def execute_sql_query(sql_file_path: str) -> List[Tuple[Any, ...]]:
    """Helper function to execute SQL queries"""
    try:
        with psycopg.connect(con_str, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(read_from_sql_file(sql_file_path))
                return cur.fetchall()
    except Exception as e:
        logger.error(f"Error executing {sql_file_path}: {e}")
        raise


@mcp.tool()
def get_all_charging_sessions_summary() -> List[Tuple[Any, ...]]:
    """
    Get the summary of all charging sessions for each car.
    """
    return execute_sql_query("queries/all_charging_sessions_summary.sql")


@mcp.tool()
def get_average_efficiency_by_temperature() -> List[Tuple[Any, ...]]:
    """
    Get the average efficiency by temperature for each car.
    """
    return execute_sql_query("queries/average_efficiency_by_temperature.sql")


@mcp.tool()
def get_basic_car_information() -> List[Tuple[Any, ...]]:
    """
    Get the basic car information for each car.
    """
    return execute_sql_query("queries/basic_car_information.sql")


@mcp.tool()
def get_battery_degradation_over_time() -> List[Tuple[Any, ...]]:
    """
    Get the battery degradation over time for each car.
    """
    return execute_sql_query("queries/battery_degradation_over_time.sql")


@mcp.tool()
def get_battery_health_summary() -> List[Tuple[Any, ...]]:
    """
    Get the battery health summary for each car.
    """
    return execute_sql_query("queries/battery_health_summary.sql")


@mcp.tool()
def get_charging_by_location() -> List[Tuple[Any, ...]]:
    """
    Get the charging by location for each car.
    """
    return execute_sql_query("queries/charging_by_location.sql")


@mcp.tool()
def get_current_car_status() -> List[Tuple[Any, ...]]:
    """
    Get the current car status for each car.
    """
    return execute_sql_query("queries/current_car_status.sql")


@mcp.tool()
def get_daily_battery_usage_patterns() -> List[Tuple[Any, ...]]:
    """
    Get the daily battery usage patterns for each car.
    """
    return execute_sql_query("queries/daily_battery_usage_patterns.sql")


@mcp.tool()
def get_daily_driving_patterns() -> List[Tuple[Any, ...]]:
    """
    Get the daily driving patterns for each car.
    """
    return execute_sql_query("queries/daily_driving_patterns.sql")


@mcp.tool()
def get_drive_summary_per_day() -> List[Tuple[Any, ...]]:
    """
    Get the drive summary per day for each car.
    """
    return execute_sql_query("queries/drive_summary_per_day.sql")


@mcp.tool()
def get_efficiency_by_month_and_temperature() -> List[Tuple[Any, ...]]:
    """
    Get the efficiency by month and temperature for each car.
    """
    return execute_sql_query("queries/efficiency_by_month_and_temperature.sql")


@mcp.tool()
def get_longest_drives_by_distance() -> List[Tuple[Any, ...]]:
    """
    Get the longest drives by distance for each car.
    """
    return execute_sql_query("queries/longest_drives_by_distance.sql")


@mcp.tool()
def get_monthly_driving_summary() -> List[Tuple[Any, ...]]:
    """
    Get the monthly driving summary for each car.
    """
    return execute_sql_query("queries/monthly_driving_summary.sql")


@mcp.tool()
def get_most_visited_locations() -> List[Tuple[Any, ...]]:
    """
    Get the most visited locations for each car.
    """
    return execute_sql_query("queries/most_visited_locations.sql")


@mcp.tool()
def get_software_update_history() -> List[Tuple[Any, ...]]:
    """
    Get the software update history for each car.
    """
    return execute_sql_query("queries/software_update_history.sql")


@mcp.tool()
def get_tire_pressure_weekly_trends() -> List[Tuple[Any, ...]]:
    """
    Get the tire pressure weekly trends for each car.
    """
    return execute_sql_query("queries/tire_pressure_weekly_trends.sql")


@mcp.tool()
def get_total_distance_and_efficiency() -> List[Tuple[Any, ...]]:
    """
    Get the total distance and efficiency for each car.
    """
    return execute_sql_query("queries/total_distance_and_efficiency.sql")


@mcp.tool()
def get_unusual_power_consumption() -> List[Tuple[Any, ...]]:
    """
    Get the unusual power consumption for each car.
    """
    return execute_sql_query("queries/unusual_power_consumption.sql")


if __name__ == "__main__":
    mcp.run(transport="stdio")
