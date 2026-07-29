"""Tests for the opt-in set_charging_cost write tool."""

from __future__ import annotations

import psycopg
import pytest

from teslamate_mcp.config import Settings
from teslamate_mcp.db import build_pool, execute_write
from teslamate_mcp.server import create_server

_DUMMY_DB_URL = "postgresql://teslamate:secret@example.test/teslamate"


@pytest.mark.asyncio
async def test_write_tool_absent_by_default() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL)  # type: ignore[call-arg]
    mcp = create_server(settings)
    names = {tool.name for tool in await mcp.list_tools()}
    assert "set_charging_cost" not in names


@pytest.mark.asyncio
async def test_write_tool_schema_when_enabled() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL, enable_charging_writes=True)  # type: ignore[call-arg]
    mcp = create_server(settings)
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    tool = tools["set_charging_cost"]
    schema = tool.input_schema
    assert sorted(schema["required"]) == ["charging_process_id", "cost"]
    assert "ctx" not in schema.get("properties", {})
    assert schema["properties"]["cost"]["minimum"] == 0
    assert tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is True

    prompts = {p.name for p in await mcp.list_prompts()}
    assert "backfill_costs_from_receipts" in prompts


@pytest.mark.asyncio
async def test_receipt_prompt_absent_by_default() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL)  # type: ignore[call-arg]
    mcp = create_server(settings)
    prompts = {p.name for p in await mcp.list_prompts()}
    assert "backfill_costs_from_receipts" not in prompts


async def test_set_charging_cost_e2e(mcp_session) -> None:
    async with mcp_session(enable_charging_writes=True) as session:
        # Seeded session 3 (Red Rocket) has cost NULL.
        result = await session.call_tool(
            "set_charging_cost", {"charging_process_id": 3, "cost": 42.5}
        )
        assert not result.is_error, [getattr(c, "text", c) for c in result.content]
        (row,) = result.structured_content["result"]
        assert row["charging_process_id"] == 3
        assert row["cost"] == 42.5

        # The change is committed and visible to the read tools.
        costs = await session.call_tool("get_charging_costs", {"group_by": "car"})
        by_key = {r["group_key"]: r for r in costs.structured_content["result"]}
        assert by_key["Red Rocket"]["total_cost"] == 42.5

        unknown = await session.call_tool(
            "set_charging_cost", {"charging_process_id": 999999, "cost": 5}
        )
        assert unknown.is_error

        negative = await session.call_tool(
            "set_charging_cost", {"charging_process_id": 3, "cost": -1}
        )
        assert negative.is_error  # pydantic ge=0


async def test_column_scoped_grant_is_the_real_boundary(pool, database_url) -> None:
    """A role with UPDATE (cost) only can set costs but nothing else."""
    async with pool.connection() as conn:
        await conn.execute("DROP ROLE IF EXISTS mcp_cost_writer")
        await conn.execute("CREATE ROLE mcp_cost_writer LOGIN PASSWORD 'pw'")
        await conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_cost_writer")
        await conn.execute("GRANT UPDATE (cost) ON charging_processes TO mcp_cost_writer")

    restricted_url = database_url.replace("test:test@", "mcp_cost_writer:pw@")
    assert restricted_url != database_url, "unexpected testcontainer credentials"
    settings = Settings(database_url=restricted_url)  # type: ignore[call-arg]
    restricted = build_pool(settings)
    await restricted.open()
    try:
        rows = await execute_write(
            restricted,
            "UPDATE charging_processes SET cost = %(c)s::numeric(10,2)"
            " WHERE id = %(id)s::int RETURNING id, cost",
            {"c": 7.5, "id": 1},
        )
        assert rows and rows[0]["cost"] == 7.5

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await execute_write(
                restricted,
                "UPDATE charging_processes SET duration_min = %(d)s::int"
                " WHERE id = %(id)s::int RETURNING id",
                {"d": 1, "id": 1},
            )
    finally:
        await restricted.close()
