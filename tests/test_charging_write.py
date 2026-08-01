"""Tests for the opt-in set_charging_cost write tool."""

from __future__ import annotations

import psycopg
import pytest
from mcp.types import ElicitResult

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
    # The Resolve-marked confirmation param is framework-filled, never client-facing.
    assert "confirmation" not in schema.get("properties", {})
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


async def test_confirm_accept_writes(mcp_session) -> None:
    """A client with form elicitation gets asked; accepting performs the write."""
    asked: list[str] = []

    async def approve(context, params):
        asked.append(params.message)
        return ElicitResult(action="accept", content={"confirm": True})

    async with mcp_session(enable_charging_writes=True, elicitation_callback=approve) as session:
        result = await session.call_tool(
            "set_charging_cost", {"charging_process_id": 3, "cost": 9.75}
        )
        assert not result.is_error, [getattr(c, "text", c) for c in result.content]
        (row,) = result.structured_content["result"]
        assert row["cost"] == 9.75
    assert len(asked) == 1
    assert "#3" in asked[0] and "9.75" in asked[0]


async def test_confirm_decline_blocks_write(mcp_session) -> None:
    async def decline(context, params):
        return ElicitResult(action="decline")

    async with mcp_session(enable_charging_writes=True, elicitation_callback=decline) as session:
        result = await session.call_tool(
            "set_charging_cost", {"charging_process_id": 3, "cost": 9.75}
        )
        assert result.is_error

        # The seeded NULL cost is untouched.
        sessions = await session.call_tool("search_charging_sessions", {"car_name": "red"})
        (row,) = sessions.structured_content["result"]
        assert row["cost"] is None


async def test_confirm_answered_no_blocks_write(mcp_session) -> None:
    async def answer_no(context, params):
        return ElicitResult(action="accept", content={"confirm": False})

    async with mcp_session(enable_charging_writes=True, elicitation_callback=answer_no) as session:
        result = await session.call_tool(
            "set_charging_cost", {"charging_process_id": 3, "cost": 9.75}
        )
        assert result.is_error

        sessions = await session.call_tool("search_charging_sessions", {"car_name": "red"})
        (row,) = sessions.structured_content["result"]
        assert row["cost"] is None


async def test_no_elicitation_capability_degrades_to_direct_write(mcp_session) -> None:
    """Clients without form elicitation (e.g. the portal today) keep the
    pre-0.9 behavior: the write proceeds without a confirmation round."""
    async with mcp_session(enable_charging_writes=True) as session:
        result = await session.call_tool(
            "set_charging_cost", {"charging_process_id": 3, "cost": 5.25}
        )
        assert not result.is_error, [getattr(c, "text", c) for c in result.content]
        (row,) = result.structured_content["result"]
        assert row["cost"] == 5.25


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
