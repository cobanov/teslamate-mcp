"""Test script for TeslaMate MCP Server"""

import asyncio
import json

from fastmcp import Client


async def test_tool(client: Client, tool_name: str):
    """Test a single tool"""
    result = await client.call_tool(tool_name)
    data = result.structured_content["result"]
    count = len(data)

    print(f"  ✓ {tool_name:<35} ({count} result{'s' if count != 1 else ''})")
    if data:
        print(f"    {json.dumps(data[0], indent=2, default=str)}")


async def test_server():
    """Test TeslaMate MCP Server tools"""
    client = Client("main.py")

    async with client:
        print("TeslaMate MCP Server - Test Suite\n")

        tools = [
            "get_basic_car_information",
            "get_current_car_status",
            "get_battery_health_summary",
        ]

        for tool in tools:
            await test_tool(client, tool)
            print()


if __name__ == "__main__":
    asyncio.run(test_server())
