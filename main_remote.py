import contextlib
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import click
import mcp.types as types
import psycopg
import uvicorn
from dotenv import load_dotenv
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Application context with database pool"""

    db_pool: AsyncConnectionPool


# Global app context
app_context: AppContext | None = None


# Load database schema information
def load_db_schema() -> List[Dict[str, str]]:
    """Load database schema from JSON file"""
    try:
        with open("all_db_info.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Database schema file all_db_info.json not found")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing database schema: {e}")
        return []


# Cache the database schema
DB_SCHEMA = load_db_schema()


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Bearer token authentication middleware for the MCP server"""

    def __init__(self, app, auth_token: Optional[str] = None):
        super().__init__(app)
        self.auth_token = auth_token

    async def dispatch(self, request, call_next):
        # Skip auth if no token is configured
        if not self.auth_token:
            return await call_next(request)

        # Skip auth for non-MCP endpoints
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Authorization required"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate token
        try:
            provided_token = auth_header.split(" ", 1)[1]
            if provided_token != self.auth_token:
                raise ValueError("Invalid token")
        except (IndexError, ValueError):
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Continue with the request
        return await call_next(request)


def validate_sql_query(sql: str) -> tuple[bool, Optional[str]]:
    """
    Validate SQL query to ensure it's read-only
    Returns (is_valid, error_message)
    """
    # Remove SQL comments
    # Remove single-line comments
    sql_no_comments = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    # Remove multi-line comments
    sql_no_comments = re.sub(r"/\*.*?\*/", "", sql_no_comments, flags=re.DOTALL)

    # Remove string literals to avoid false positives
    # This is a simplified approach - a full SQL parser would be more accurate
    sql_no_strings = re.sub(r"'[^']*'", "''", sql_no_comments)
    sql_no_strings = re.sub(r'"[^"]*"', '""', sql_no_strings)

    # Check for forbidden operations in the cleaned SQL
    forbidden_pattern = (
        r"\b(DROP|CREATE|INSERT|UPDATE|DELETE|ALTER|TRUNCATE|GRANT|REVOKE)\b"
    )
    if re.search(forbidden_pattern, sql_no_strings, re.IGNORECASE):
        return (
            False,
            f"Forbidden SQL operation detected. Only SELECT queries are allowed.",
        )

    # Check for EXEC/EXECUTE
    if re.search(r"\b(EXEC|EXECUTE)\s*\(", sql_no_strings, re.IGNORECASE):
        return (
            False,
            f"Forbidden SQL operation detected. Only SELECT queries are allowed.",
        )

    # Basic check for SELECT statement
    if not re.search(r"^\s*SELECT\b", sql_no_comments.strip(), re.IGNORECASE):
        return False, "Only SELECT statements are allowed."

    # Check for semicolons that might indicate multiple statements
    cleaned = sql_no_comments.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1]  # Remove trailing semicolon

    if ";" in cleaned:
        return False, "Multiple SQL statements are not allowed."

    return True, None


async def read_from_sql_file(file_path: str) -> str:
    """Read SQL query from file"""
    try:
        with open(file_path, "r") as file:
            return file.read()
    except FileNotFoundError:
        logger.error(f"SQL file not found: {file_path}")
        raise
    except IOError as e:
        logger.error(f"Error reading SQL file {file_path}: {e}")
        raise


async def execute_sql_query(sql_file_path: str) -> List[Dict[str, Any]]:
    """Execute SQL query using connection pool"""
    try:
        if not app_context:
            raise RuntimeError("Application context not initialized")

        # Read SQL query
        sql_query = await read_from_sql_file(sql_file_path)

        # Execute query using pool
        async with app_context.db_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql_query)
                results = await cur.fetchall()
                return results
    except Exception as e:
        logger.error(f"Error executing {sql_file_path}: {e}")
        raise


@click.command()
@click.option("--port", default=8888, help="Port to listen on for HTTP")
@click.option(
    "--host",
    default="0.0.0.0",
    help="Host to listen on",
)
@click.option(
    "--log-level",
    default="INFO",
    help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
)
@click.option(
    "--json-response",
    is_flag=True,
    default=False,
    help="Enable JSON responses instead of SSE streams",
)
@click.option(
    "--auth-token",
    default=None,
    help="Bearer authentication token (optional)",
    envvar="AUTH_TOKEN",
)
def main(
    port: int,
    host: str,
    log_level: str,
    json_response: bool,
    auth_token: str | None,
) -> int:
    global app_context

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create MCP server
    app = Server("teslamate")

    # Register all tools
    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.ContentBlock]:
        """Route tool calls to appropriate handlers"""

        tool_handlers = {
            "get_all_charging_sessions_summary": get_all_charging_sessions_summary,
            "get_average_efficiency_by_temperature": get_average_efficiency_by_temperature,
            "get_basic_car_information": get_basic_car_information,
            "get_battery_degradation_over_time": get_battery_degradation_over_time,
            "get_battery_health_summary": get_battery_health_summary,
            "get_charging_by_location": get_charging_by_location,
            "get_current_car_status": get_current_car_status,
            "get_daily_battery_usage_patterns": get_daily_battery_usage_patterns,
            "get_daily_driving_patterns": get_daily_driving_patterns,
            "get_drive_summary_per_day": get_drive_summary_per_day,
            "get_efficiency_by_month_and_temperature": get_efficiency_by_month_and_temperature,
            "get_longest_drives_by_distance": get_longest_drives_by_distance,
            "get_monthly_driving_summary": get_monthly_driving_summary,
            "get_most_visited_locations": get_most_visited_locations,
            "get_software_update_history": get_software_update_history,
            "get_tire_pressure_weekly_trends": get_tire_pressure_weekly_trends,
            "get_total_distance_and_efficiency": get_total_distance_and_efficiency,
            "get_unusual_power_consumption": get_unusual_power_consumption,
            "get_database_schema": get_database_schema,
            "run_sql": run_sql,
        }

        if name not in tool_handlers:
            raise ValueError(f"Unknown tool: {name}")

        # Call the appropriate handler
        if name == "run_sql":
            # run_sql requires a query argument
            query = arguments.get("query")
            if not query:
                raise ValueError("Missing required argument 'query' for run_sql")
            result = await tool_handlers[name](query)
        else:
            # Other handlers don't take arguments
            result = await tool_handlers[name]()

        # Convert result to MCP content blocks
        import json

        return [
            types.TextContent(
                type="text",
                text=json.dumps(
                    result, indent=2, default=str
                ),  # Convert to JSON string
            )
        ]

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        """List all available TeslaMate tools"""
        return [
            types.Tool(
                name="get_all_charging_sessions_summary",
                description="Get the summary of all charging sessions for each car. Returns charging statistics including total sessions, energy consumed, and costs.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_average_efficiency_by_temperature",
                description="Get the average efficiency by temperature for each car. Helps understand how temperature affects vehicle efficiency.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_basic_car_information",
                description="Get the basic car information for each car. Returns VIN, model, firmware version, and other vehicle details.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_battery_degradation_over_time",
                description="Get the battery degradation over time for each car. Tracks battery health metrics and capacity changes.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_battery_health_summary",
                description="Get the battery health summary for each car. Provides current battery health status and statistics.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_charging_by_location",
                description="Get the charging by location for each car. Shows charging patterns and statistics grouped by location.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_current_car_status",
                description="Get the current car status for each car. Returns real-time vehicle status including location, battery level, and state.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_daily_battery_usage_patterns",
                description="Get the daily battery usage patterns for each car. Analyzes battery consumption patterns throughout the day.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_daily_driving_patterns",
                description="Get the daily driving patterns for each car. Shows driving habits and patterns by day of week and time.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_drive_summary_per_day",
                description="Get the drive summary per day for each car. Provides daily driving statistics including distance, duration, and efficiency.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_efficiency_by_month_and_temperature",
                description="Get the efficiency by month and temperature for each car. Analyzes how seasonal temperature changes affect vehicle efficiency.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_longest_drives_by_distance",
                description="Get the longest drives by distance for each car. Lists the longest trips taken with details about distance and duration.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_monthly_driving_summary",
                description="Get the monthly driving summary for each car. Provides monthly statistics for distance, energy usage, and costs.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_most_visited_locations",
                description="Get the most visited locations for each car. Shows frequently visited places with visit counts and durations.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_software_update_history",
                description="Get the software update history for each car. Tracks firmware updates and version changes over time.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_tire_pressure_weekly_trends",
                description="Get the tire pressure weekly trends for each car. Monitors tire pressure changes and patterns by week.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_total_distance_and_efficiency",
                description="Get the total distance and efficiency for each car. Provides lifetime statistics for distance traveled and energy efficiency.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_unusual_power_consumption",
                description="Get the unusual power consumption for each car. Identifies anomalies in power usage that might indicate issues.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_database_schema",
                description="Get the TeslaMate database schema information including all tables and columns with their data types. Use this to understand the database structure before writing SQL queries.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="run_sql",
                description="Execute a custom SELECT SQL query on the TeslaMate database. Only SELECT queries are allowed. Use get_database_schema first to understand the available tables and columns.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The SELECT SQL query to execute. Must be a single SELECT statement.",
                        }
                    },
                    "required": ["query"],
                },
            ),
        ]

    # Tool handler functions
    async def get_all_charging_sessions_summary() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/all_charging_sessions_summary.sql")

    async def get_average_efficiency_by_temperature() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/average_efficiency_by_temperature.sql")

    async def get_basic_car_information() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/basic_car_information.sql")

    async def get_battery_degradation_over_time() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/battery_degredation_overt_time.sql")

    async def get_battery_health_summary() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/battery_health_summary.sql")

    async def get_charging_by_location() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/charging_by_location.sql")

    async def get_current_car_status() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/current_car_status.sql")

    async def get_daily_battery_usage_patterns() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/daily_battery_usage.sql")

    async def get_daily_driving_patterns() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/daily_driving_patterns.sql")

    async def get_drive_summary_per_day() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/drive_summary_per_day.sql")

    async def get_efficiency_by_month_and_temperature() -> List[Dict[str, Any]]:
        return await execute_sql_query(
            "queries/efficiency_by_month_and_temperature.sql"
        )

    async def get_longest_drives_by_distance() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/longest_drives_by_distance.sql")

    async def get_monthly_driving_summary() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/monthly_driving_summary.sql")

    async def get_most_visited_locations() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/most_visited_locations.sql")

    async def get_software_update_history() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/software_update_history.sql")

    async def get_tire_pressure_weekly_trends() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/tire_pressure_weekly_trend.sql")

    async def get_total_distance_and_efficiency() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/total_distance_and_efficiency.sql")

    async def get_unusual_power_consumption() -> List[Dict[str, Any]]:
        return await execute_sql_query("queries/unusual_power_consumption.sql")

    async def get_database_schema() -> List[Dict[str, str]]:
        """Return the database schema information"""
        return DB_SCHEMA

    async def run_sql(query: str) -> List[Dict[str, Any]]:
        """Execute a custom SQL query with validation"""
        # Validate the SQL query
        is_valid, error_msg = validate_sql_query(query)
        if not is_valid:
            raise ValueError(error_msg)

        try:
            if not app_context:
                raise RuntimeError("Application context not initialized")

            # Execute query using pool
            async with app_context.db_pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query)
                    results = await cur.fetchall()
                    return results
        except psycopg.errors.SyntaxError as e:
            raise ValueError(f"SQL syntax error: {e}")
        except psycopg.errors.UndefinedTable as e:
            raise ValueError(f"Table not found: {e}")
        except psycopg.errors.UndefinedColumn as e:
            raise ValueError(f"Column not found: {e}")
        except Exception as e:
            logger.error(f"Error executing SQL query: {e}")
            raise ValueError(f"Database error: {str(e)}")

    # Create the session manager with true stateless mode
    session_manager = StreamableHTTPSessionManager(
        app=app,
        event_store=None,
        json_response=json_response,
        stateless=True,
    )

    async def handle_streamable_http(
        scope: Scope, receive: Receive, send: Send
    ) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        """Context manager for application lifecycle"""
        global app_context

        # Get database connection string
        con_str = os.getenv("DATABASE_URL")
        if not con_str:
            raise ValueError("DATABASE_URL environment variable is required")

        # Create connection pool
        db_pool = AsyncConnectionPool(
            con_str, min_size=1, max_size=10, kwargs={"row_factory": dict_row}
        )

        try:
            # Initialize the pool
            await db_pool.open()
            logger.info("Database connection pool initialized")
            app_context = AppContext(db_pool=db_pool)

            # Start session manager
            async with session_manager.run():
                logger.info("Application started with StreamableHTTP session manager!")
                yield
        finally:
            logger.info("Application shutting down...")
            if app_context:
                await app_context.db_pool.close()
                logger.info("Database connection pool closed")
                app_context = None

    # Create an ASGI application using the transport
    starlette_app = Starlette(
        debug=True,
        routes=[
            Mount("/mcp", app=handle_streamable_http),
        ],
        lifespan=lifespan,
    )

    # Add bearer auth middleware if token is provided
    if auth_token:
        starlette_app.add_middleware(BearerAuthMiddleware, auth_token=auth_token)
        logger.info("Bearer token authentication enabled")

    # Run with uvicorn
    uvicorn.run(starlette_app, host=host, port=port)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
