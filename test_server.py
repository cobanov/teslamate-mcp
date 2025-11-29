"""Test script for TeslaMate MCP Server"""

import asyncio

from fastmcp import Client


async def test_tools():
    """Test various MCP tools"""
    client = Client("main.py")

    async with client:
        print("=" * 70)
        print("Testing TeslaMate MCP Server")
        print("=" * 70)

        # Test 1: Basic car information
        print("\n[Test 1] Getting basic car information...")
        try:
            result = await client.call_tool("get_basic_car_information")
            print("✓ Success - Basic car information retrieved")
            print(result)
        except Exception as e:
            print(f"✗ Failed: {e}")

        print("\n" + "=" * 70)

        # Test 2: Current car status
        print("\n[Test 2] Getting current car status...")
        try:
            result = await client.call_tool("get_current_car_status")
            print("✓ Success - Current car status retrieved")
            print(result)
        except Exception as e:
            print(f"✗ Failed: {e}")

        print("\n" + "=" * 70)

        # Test 3: Battery health summary
        print("\n[Test 3] Getting battery health summary...")
        try:
            result = await client.call_tool("get_battery_health_summary")
            print("✓ Success - Battery health summary retrieved")
            print(result)
        except Exception as e:
            print(f"✗ Failed: {e}")

        print("\n" + "=" * 70)
        print("All tests completed!")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_tools())
