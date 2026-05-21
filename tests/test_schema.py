"""Integration test for live schema introspection (requires Docker)."""

from __future__ import annotations

from teslamate_mcp.schema import load_schema


async def test_load_schema_finds_demo_table(pool) -> None:
    rows = await load_schema(pool)
    tables = {(r["table_schema"], r["table_name"]) for r in rows}
    assert ("public", "demo_cars") in tables

    demo_columns = {r["column_name"] for r in rows if r["table_name"] == "demo_cars"}
    assert demo_columns == {"id", "name", "battery_kwh"}


async def test_load_schema_excludes_system_schemas(pool) -> None:
    rows = await load_schema(pool)
    schemas = {r["table_schema"] for r in rows}
    assert "pg_catalog" not in schemas
    assert "information_schema" not in schemas
