"""Database access: pooling and read-only query execution."""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import Settings
from .serialization import rows_to_jsonable


def build_pool(settings: Settings) -> AsyncConnectionPool:
    """Construct an async connection pool. Caller is responsible for `open()` and `close()`."""
    return AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        kwargs={"row_factory": dict_row},
        open=False,
    )


async def fetch_all(
    pool: AsyncConnectionPool,
    sql: str,
    params: tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    """Run a trusted query and return JSON-safe rows. Used for predefined SQL files."""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()
    return rows_to_jsonable(rows)


async def fetch_readonly(
    pool: AsyncConnectionPool,
    sql: str,
    statement_timeout_ms: int,
) -> list[dict[str, Any]]:
    """Run an untrusted query in a read-only transaction with hard timeouts.

    The PostgreSQL transaction is opened with READ ONLY, and `statement_timeout`,
    `lock_timeout`, and `idle_in_transaction_session_timeout` are set as session-
    local guards. The transaction is always rolled back, so even a query that
    bypasses Python-side checks cannot mutate the database.
    """
    async with pool.connection() as conn:
        await conn.set_autocommit(False)
        async with conn.transaction(force_rollback=True):
            async with conn.cursor() as cur:
                await cur.execute("SET TRANSACTION READ ONLY")
                await cur.execute(
                    "SET LOCAL statement_timeout = %s",
                    (str(statement_timeout_ms),),
                )
                await cur.execute("SET LOCAL lock_timeout = %s", ("2000",))
                await cur.execute(
                    "SET LOCAL idle_in_transaction_session_timeout = %s",
                    (str(statement_timeout_ms),),
                )
                await cur.execute(sql)
                rows = await cur.fetchall()
    return rows_to_jsonable(rows)
