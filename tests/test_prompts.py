"""Tests for the canned prompts, including the prompt->tool-name cross-check.

Prompts embed tool names as backticked strings, so renaming a query's .toml
`name` silently breaks the reference at runtime. The cross-check here renders
every prompt and asserts each referenced name is a registered tool, turning
that silent drift into a CI failure.
"""

from __future__ import annotations

import re

import pytest

from teslamate_mcp.config import Settings
from teslamate_mcp.server import create_server

_DUMMY_DB_URL = "postgresql://teslamate:secret@example.test/teslamate"

# Backticked tool references: `get_*`, `search_*`, `set_*`, `show_*`, `run_sql`.
_TOOL_REF_RE = re.compile(r"`((?:get_|search_|set_|show_)[a-z0-9_]+|run_sql)`")

_EXPECTED_PROMPTS = {
    "analyze_battery_health",
    "summarize_driving",
    "analyze_charging",
    "find_anomalies",
    "weather_efficiency",
    "status_report",
}


@pytest.mark.asyncio
async def test_prompts_registered() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL)  # type: ignore[call-arg]
    mcp = create_server(settings)
    names = {p.name for p in await mcp.list_prompts()}
    assert names == _EXPECTED_PROMPTS


@pytest.mark.asyncio
async def test_prompts_with_writes_enabled() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL, enable_charging_writes=True)  # type: ignore[call-arg]
    mcp = create_server(settings)
    names = {p.name for p in await mcp.list_prompts()}
    assert names == _EXPECTED_PROMPTS | {"backfill_costs_from_receipts"}


@pytest.mark.asyncio
async def test_every_prompt_tool_reference_resolves() -> None:
    # Writes enabled so the receipts prompt (which references set_charging_cost)
    # is rendered and checked too.
    settings = Settings(database_url=_DUMMY_DB_URL, enable_charging_writes=True)  # type: ignore[call-arg]
    mcp = create_server(settings)
    tool_names = {t.name for t in await mcp.list_tools()}

    for prompt in await mcp.list_prompts():
        result = await mcp.get_prompt(prompt.name)
        text = result.model_dump_json()
        referenced = set(_TOOL_REF_RE.findall(text))
        assert referenced, f"prompt {prompt.name} references no tools"
        missing = referenced - tool_names
        assert not missing, f"prompt {prompt.name} references unknown tools: {sorted(missing)}"


@pytest.mark.asyncio
async def test_summarize_driving_window_argument_binds() -> None:
    settings = Settings(database_url=_DUMMY_DB_URL)  # type: ignore[call-arg]
    mcp = create_server(settings)
    result = await mcp.get_prompt("summarize_driving", {"window": "last 7 days"})
    assert "last 7 days" in result.model_dump_json()
