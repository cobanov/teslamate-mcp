"""Database access: pooling and read-only query execution."""

from __future__ import annotations

from typing import Any

from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import Settings
from .serialization import rows_to_jsonable


def build_pool(settings: Settings) -> AsyncConnectionPool:
    """Construct an async connection pool. Caller is responsible for `open()` and `close()`.

    A libpq-level `statement_timeout` bounds every query the pool runs. The
    bundled reports go through `fetch_all`, which sets no timeout of its own,
    so before this a pathological query pinned a backend indefinitely: the MCP
    client hung with no error while PostgreSQL kept burning CPU, and killing
    the client did not cancel the server-side query. `fetch_readonly` still
    narrows the bound further with SET LOCAL for untrusted SQL.
    """
    kwargs: dict[str, Any] = {"row_factory": dict_row}
    # kwargs win over conninfo, so only inject when the operator has not set
    # their own libpq options in DATABASE_URL.
    if "options=" not in settings.database_url:
        kwargs["options"] = f"-c statement_timeout={int(settings.statement_timeout_ms)}"
    return AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        kwargs=kwargs,
        open=False,
    )


async def fetch_all(
    pool: AsyncConnectionPool,
    query: str,
    params: tuple[Any, ...] | dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run a trusted query and return JSON-safe rows. Used for predefined SQL files.

    Dict params bind to `%(name)s` placeholders. When params is not None, literal
    percent signs in the SQL must be escaped as `%%`.
    """
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(query, params)
        rows = await cur.fetchall()
    return rows_to_jsonable(rows)


async def execute_write(
    pool: AsyncConnectionPool,
    query: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run a trusted, parameterized write and COMMIT; return RETURNING rows.

    This is the ONLY sanctioned write path in the codebase. Callers are
    hand-written tools gated by Settings.enable_charging_writes; the DB role's
    column-scoped grant (e.g. UPDATE (cost) ON charging_processes) is the real
    boundary. Never route user-supplied SQL through here.
    """
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(query, params)
        rows = await cur.fetchall() if cur.description is not None else []
    return rows_to_jsonable(rows)


async def fetch_readonly(
    pool: AsyncConnectionPool,
    query: str,
    statement_timeout_ms: int,
) -> list[dict[str, Any]]:
    """Run an untrusted query in a read-only transaction with hard timeouts.

    The PostgreSQL transaction is opened with READ ONLY, and `statement_timeout`,
    `lock_timeout`, and `idle_in_transaction_session_timeout` are set as session-
    local guards. The transaction is always rolled back, so even a query that
    bypasses Python-side checks cannot mutate the database.
    """
    # SET LOCAL refuses parameter binding, so the timeout must be inlined as a
    # literal. int() casts make any non-integer fail loudly before reaching PG.
    stmt_ms = int(statement_timeout_ms)
    lock_ms = 2000

    async with pool.connection() as conn:
        await conn.set_autocommit(False)
        async with conn.transaction(force_rollback=True), conn.cursor() as cur:
            await cur.execute("SET TRANSACTION READ ONLY")
            await cur.execute(
                sql.SQL("SET LOCAL statement_timeout = {ms}").format(ms=sql.Literal(stmt_ms))
            )
            await cur.execute(
                sql.SQL("SET LOCAL lock_timeout = {ms}").format(ms=sql.Literal(lock_ms))
            )
            await cur.execute(
                sql.SQL("SET LOCAL idle_in_transaction_session_timeout = {ms}").format(
                    ms=sql.Literal(stmt_ms)
                )
            )
            await cur.execute(query)
            rows = await cur.fetchall()
    return rows_to_jsonable(rows)
