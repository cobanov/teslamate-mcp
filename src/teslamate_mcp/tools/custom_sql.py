"""The `run_sql` tool: untrusted user SQL executed under PG-level guardrails."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..db import fetch_readonly

logger = logging.getLogger(__name__)

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|"
    r"COPY|VACUUM|CLUSTER|REINDEX|REFRESH|CALL|DO|EXECUTE|LISTEN|NOTIFY|"
    r"LOCK|SECURITY|RESET|DISCARD|CHECKPOINT)\b",
    re.IGNORECASE,
)

_COMMENT_LINE = re.compile(r"--.*$", re.MULTILINE)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_SINGLE = re.compile(r"'(?:''|[^'])*'")
_STRING_DOUBLE = re.compile(r'"(?:""|[^"])*"')

_HAS_LIMIT = re.compile(r"\bLIMIT\b\s+\d+", re.IGNORECASE)


class SqlValidationError(ValueError):
    """Raised when a user-supplied SQL query fails the cheap pre-check."""


def _strip_safe(sql: str) -> str:
    """Remove comments and string literals so keyword detection doesn't false-positive."""
    s = _COMMENT_BLOCK.sub("", sql)
    s = _COMMENT_LINE.sub("", s)
    s = _STRING_SINGLE.sub("''", s)
    s = _STRING_DOUBLE.sub('""', s)
    return s


def validate_sql(sql: str) -> None:
    """Cheap first-line defense. The PG read-only transaction is the real guarantee."""
    stripped = sql.strip()
    if not stripped:
        raise SqlValidationError("Query is empty")

    clean = _strip_safe(stripped).strip()
    if not clean:
        raise SqlValidationError("Query contains no executable statement")

    # Reject multi-statement queries. A trailing ';' is fine; ';' in the middle is not.
    body = clean.rstrip().rstrip(";")
    if ";" in body:
        raise SqlValidationError("Multiple SQL statements are not allowed")

    leading_word = re.match(r"\s*([A-Za-z]+)", body)
    if leading_word is None:
        raise SqlValidationError("Query must start with SELECT or WITH")
    first_keyword = leading_word.group(1).upper()
    if first_keyword not in {"SELECT", "WITH"}:
        raise SqlValidationError("Only SELECT or WITH ... SELECT queries are allowed")

    if _FORBIDDEN_KEYWORDS.search(body):
        raise SqlValidationError("Query contains a forbidden keyword")


def enforce_limit(sql: str, default_limit: int) -> str:
    """Wrap the query in a subquery with LIMIT if it has no LIMIT of its own.

    Wrapping (instead of appending) keeps the user's ORDER BY semantics correct
    and works even when the query is a CTE that ends with a SELECT.
    """
    body = sql.strip().rstrip(";").rstrip()
    if _HAS_LIMIT.search(body):
        return body
    return f"SELECT * FROM ({body}) AS _capped LIMIT {default_limit}"


def register_custom_sql(
    mcp: MCPServer,
    *,
    statement_timeout_ms: int,
    row_limit: int,
) -> None:
    """Register the `run_sql` tool on the given server."""

    annotations = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )

    description = (
        "Execute a custom read-only SQL query against the TeslaMate database. "
        "Only SELECT (and WITH ... SELECT) statements are accepted. The query "
        "runs in a READ ONLY transaction with statement_timeout enforced; if "
        "no LIMIT is supplied, the result is automatically capped. Call "
        "`get_database_schema` first to learn the available tables and columns."
    )

    async def run_sql(
        ctx: Context,
        query: str = Field(
            ...,
            description="A single SELECT or WITH...SELECT statement.",
            min_length=1,
        ),
    ) -> list[dict[str, Any]]:
        try:
            validate_sql(query)
        except SqlValidationError as exc:
            logger.warning("run_sql rejected query: %s", exc)
            raise
        capped = enforce_limit(query, row_limit)
        pool = ctx.request_context.lifespan_context.pool

        logger.info(
            "run_sql executing %d-char query (timeout %dms)", len(query), statement_timeout_ms
        )
        start = time.perf_counter()
        rows = await fetch_readonly(pool, capped, statement_timeout_ms)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.info("run_sql returned %d row(s) in %dms", len(rows), elapsed_ms)
        return rows

    run_sql.__annotations__["ctx"] = Context
    mcp.tool(name="run_sql", description=description, annotations=annotations)(run_sql)
