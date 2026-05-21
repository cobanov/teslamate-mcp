"""Unit tests for predefined-tool discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from teslamate_mcp.tools.registry import discover_predefined_tools


def test_discover_finds_all_eighteen_bundled_tools() -> None:
    tools = discover_predefined_tools()
    names = {t.name for t in tools}
    assert len(tools) == 18
    # Spot-check that a few expected tools are present.
    assert "get_basic_car_information" in names
    assert "get_battery_health_summary" in names
    assert "get_unusual_power_consumption" in names


def test_each_tool_has_nonempty_metadata() -> None:
    for tool in discover_predefined_tools():
        assert tool.name.startswith("get_")
        assert len(tool.description) > 20
        assert tool.sql.strip().upper().startswith(("SELECT", "WITH"))


def test_missing_sidecar_raises(tmp_path: Path) -> None:
    (tmp_path / "orphan.sql").write_text("SELECT 1", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Missing sidecar"):
        discover_predefined_tools(tmp_path)


def test_malformed_sidecar_raises(tmp_path: Path) -> None:
    (tmp_path / "q.sql").write_text("SELECT 1", encoding="utf-8")
    (tmp_path / "q.toml").write_text('name = "x"\n', encoding="utf-8")  # missing description
    with pytest.raises(ValueError, match="description"):
        discover_predefined_tools(tmp_path)
