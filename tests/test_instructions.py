"""Server instructions: every tool they name exists, and they follow the settings."""

from __future__ import annotations

import pytest

from teslamate_mcp.config import Settings
from teslamate_mcp.server import create_server
from tests.test_prompts import _TOOL_REF_RE

_DUMMY_DB_URL = "postgresql://teslamate:secret@example.test/teslamate"


@pytest.mark.asyncio
@pytest.mark.parametrize("writes", [False, True])
async def test_instruction_tool_references_resolve(writes: bool) -> None:
    settings = Settings(database_url=_DUMMY_DB_URL, enable_charging_writes=writes)  # type: ignore[call-arg]
    mcp = create_server(settings)
    tool_names = {t.name for t in await mcp.list_tools()}
    referenced = set(_TOOL_REF_RE.findall(mcp.instructions or ""))
    assert len(referenced) > 15
    assert not referenced - tool_names, sorted(referenced - tool_names)
    assert ("`set_charging_cost`" in mcp.instructions) is writes


def test_instructions_name_the_report_timezone() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL, report_timezone="Europe/Istanbul")  # type: ignore[call-arg]
    assert "Europe/Istanbul" in (create_server(settings).instructions or "")


async def test_clients_receive_the_instructions(mcp_session) -> None:
    async with mcp_session() as session:
        instructions = session.instructions
    assert instructions and "`get_unit_preferences`" in instructions
