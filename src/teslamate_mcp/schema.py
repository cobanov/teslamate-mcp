"""Live database schema introspection."""

from __future__ import annotations

from typing import Any

from psycopg_pool import AsyncConnectionPool

from .db import fetch_all

_SCHEMA_QUERY = """
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable,
    ordinal_position
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
  AND table_schema NOT LIKE 'pg_%'
ORDER BY table_schema, table_name, ordinal_position
"""


async def load_schema(pool: AsyncConnectionPool) -> list[dict[str, Any]]:
    """Query `information_schema.columns` and return one row per column."""
    return await fetch_all(pool, _SCHEMA_QUERY)
