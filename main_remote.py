"""TeslaMate MCP Server - HTTP Transport (Remote)"""

import contextlib
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import click
import mcp.types as types
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from psycopg_pool import AsyncConnectionPool
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from src.config import Config
from src.database import DatabaseManager, create_async_pool
from src.tools import TOOL_DEFINITIONS, get_tool_by_name
from src.validators import validate_sql_query

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Application context with database pool and manager"""

    db_pool: AsyncConnectionPool
    db_manager: DatabaseManager
    db_schema: List[Dict[str, str]]


# Global app context
app_context: AppContext | None = None


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


@click.command()
@click.option("--port", default=8888, help="Port to listen on for HTTP")
@click.option(
    "--host",
    default="0.0.0.0",
    help="Host to listen on",
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
    json_response: bool,
    auth_token: str | None,
) -> int:
    global app_context

    # Load configuration
    config = Config.from_env()

    # Create MCP server
    app = Server("teslamate")

    # Tool handler functions
    async def execute_predefined_tool(tool_name: str) -> List[Dict[str, Any]]:
        """Execute a predefined tool by name"""
        if not app_context:
            raise RuntimeError("Application context not initialized")

        tool = get_tool_by_name(tool_name)
        return await app_context.db_manager.execute_query_async(
            tool.sql_file, app_context.db_pool
        )

    async def get_database_schema() -> List[Dict[str, str]]:
        """Return the database schema information"""
        if not app_context:
            raise RuntimeError("Application context not initialized")
        return app_context.db_schema

    async def run_sql(query: str) -> List[Dict[str, Any]]:
        """Execute a custom SQL query with validation"""
        if not app_context:
            raise RuntimeError("Application context not initialized")

        # Validate the SQL query
        is_valid, error_msg = validate_sql_query(query)
        if not is_valid:
            raise ValueError(error_msg)

        return await app_context.db_manager.execute_custom_query_async(
            query, app_context.db_pool
        )

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.ContentBlock]:
        """Route tool calls to appropriate handlers"""

        # Handle custom SQL query tool
        if name == "run_sql":
            query = arguments.get("query")
            if not query:
                raise ValueError("Missing required argument 'query' for run_sql")
            result = await run_sql(query)
        # Handle database schema tool
        elif name == "get_database_schema":
            result = await get_database_schema()
        # Handle predefined tools
        else:
            result = await execute_predefined_tool(name)

        # Convert result to MCP content blocks
        return [
            types.TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str),
            )
        ]

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        """List all available TeslaMate tools"""
        tools = []

        # Add all predefined tools
        for tool_def in TOOL_DEFINITIONS:
            tools.append(
                types.Tool(
                    name=tool_def.name,
                    description=tool_def.description,
                    inputSchema={"type": "object", "properties": {}},
                )
            )

        # Add database schema tool
        tools.append(
            types.Tool(
                name="get_database_schema",
                description="Get the TeslaMate database schema information including all tables and columns with their data types. Use this to understand the database structure before writing SQL queries.",
                inputSchema={"type": "object", "properties": {}},
            )
        )

        # Add custom SQL query tool
        tools.append(
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
            )
        )

        return tools

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

        # Create database connection pool
        db_pool = create_async_pool(config.database_url)

        try:
            # Initialize the pool
            await db_pool.open()
            logger.info("Database connection pool initialized")

            # Load database schema
            db_schema = DatabaseManager.load_db_schema()

            # Initialize app context
            db_manager = DatabaseManager(config)
            app_context = AppContext(
                db_pool=db_pool, db_manager=db_manager, db_schema=db_schema
            )

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
    logger.info(f"Starting TeslaMate MCP server on {host}:{port}")
    uvicorn.run(starlette_app, host=host, port=port)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
