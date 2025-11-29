"""TeslaMate MCP Server - STDIO Transport (Local)"""

from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from src.teslamate_mcp.config import Config
from src.teslamate_mcp.database import DatabaseManager
from src.teslamate_mcp.tools import TOOL_DEFINITIONS

# Initialize configuration and database manager
config = Config.from_env()
logger = config.get_logger(__name__)
db_manager = DatabaseManager(config)

# Initialize MCP server
mcp = FastMCP("teslamate")


# Register all predefined query tools dynamically
def create_tool_handler(sql_file: str):
    """Factory function to create tool handlers"""

    def handler() -> List[Dict[str, Any]]:
        return db_manager.execute_query_sync(sql_file)

    return handler


# Register all tools from definitions
for tool_def in TOOL_DEFINITIONS:
    tool_func = create_tool_handler(tool_def.sql_file)
    tool_func.__doc__ = tool_def.description
    tool_func.__name__ = tool_def.name

    # Register the tool with the MCP server
    mcp.tool()(tool_func)


if __name__ == "__main__":
    logger.info("Starting TeslaMate MCP server with STDIO transport")
    mcp.run(transport="stdio")
