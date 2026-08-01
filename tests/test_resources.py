"""Tests for the teslamate:// MCP resources (query index + per-query SQL)."""

from __future__ import annotations

import json

import pytest
from mcp.server.mcpserver.exceptions import ResourceNotFoundError

from teslamate_mcp.config import Settings
from teslamate_mcp.server import create_server
from teslamate_mcp.tools.registry import discover_predefined_tools

_DUMMY_DB_URL = "postgresql://teslamate:secret@example.test/teslamate"


def _server():
    settings = Settings(database_url=_DUMMY_DB_URL)  # type: ignore[call-arg]
    return create_server(settings)


@pytest.mark.asyncio
async def test_query_index_lists_every_predefined_tool() -> None:
    mcp = _server()
    uris = {str(r.uri) for r in await mcp.list_resources()}
    assert "teslamate://queries" in uris

    (contents,) = await mcp.read_resource("teslamate://queries")
    assert contents.mime_type == "application/json"
    index = json.loads(contents.content)

    tools = discover_predefined_tools()
    assert {entry["name"] for entry in index} == {t.name for t in tools}
    for entry in index:
        assert entry["description"]
        assert entry["source"].endswith(".sql")
        assert isinstance(entry["params"], list)


@pytest.mark.asyncio
async def test_per_query_resource_returns_the_sql() -> None:
    mcp = _server()
    (contents,) = await mcp.read_resource("teslamate://queries/get_vampire_drain")
    assert "LEAD(d.start_date)" in contents.content

    by_name = {t.name: t for t in discover_predefined_tools()}
    assert contents.content == by_name["get_vampire_drain"].sql


@pytest.mark.asyncio
async def test_unknown_query_name_raises_resource_not_found() -> None:
    mcp = _server()
    with pytest.raises(ResourceNotFoundError):
        await mcp.read_resource("teslamate://queries/not_a_query")
