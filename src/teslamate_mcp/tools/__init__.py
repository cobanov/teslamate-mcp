"""MCP tool definitions for the TeslaMate server."""

from .charging_write import register_charging_write_tools
from .custom_sql import register_custom_sql
from .registry import PredefinedTool, discover_predefined_tools, register_predefined_tools
from .schema_tool import register_schema_tool

__all__ = [
    "PredefinedTool",
    "discover_predefined_tools",
    "register_charging_write_tools",
    "register_custom_sql",
    "register_predefined_tools",
    "register_schema_tool",
]
