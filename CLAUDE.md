# CLAUDE.md

## Codebase Overview

**teslamate-mcp** is a Model Context Protocol (MCP) server that exposes a TeslaMate PostgreSQL database to AI
assistants over **stdio** and **streamable HTTP**. It surfaces **25 tools** (23 predefined analytics/search
queries defined as `.sql`/`.toml` file pairs with typed optional params + `run_sql` for arbitrary read-only SQL +
`get_database_schema`), **6 prompts**, and **2 resources**. Built on the official `mcp[cli]` SDK (FastMCP) with a
`psycopg` 3 async connection pool.

**Stack**: Python 3.11+, FastMCP (`mcp[cli]`), psycopg 3 + psycopg-pool, pydantic-settings, click, Starlette/uvicorn.
Hatchling build, ruff, pytest + testcontainers. Ships as a console script and a multi-arch Docker image on GHCR.

**Structure**: `src/teslamate_mcp/` is a src-layout package — `cli.py` (entry), `server.py` (FastMCP factory +
lifespan), `db.py` (pool + two trust-level query paths), `tools/` (registry, `run_sql`, schema tool), and
`queries/` (23 bundled `.sql`+`.toml` report pairs). Tests use real Postgres via testcontainers.

**Key architectural principle — two trust levels**: bundled `.sql` files are trusted and run via the unguarded
`db.fetch_all()`; arbitrary LLM SQL (`run_sql`) runs via `db.fetch_readonly()`, whose Postgres `READ ONLY` +
forced-rollback transaction is the real security boundary (regex validation is only defense-in-depth).

**Add a new tool**: drop a `<name>.sql` + `<name>.toml` (`name`, `description`, optional `[[params]]` tables)
pair into `src/teslamate_mcp/queries/` — auto-discovered and contract-validated on restart, no code change.
Params bind as `%(name)s` placeholders (cast first occurrence; escape literal `%` as `%%`; reserved `%(tz)s`
binds `REPORT_TIMEZONE`).

**Common commands**: `uv sync`, `uv run ruff check/format src tests`, `uv run pytest`,
`uv run teslamate-mcp {stdio|http|gen-token|list-tools}`.

For detailed architecture, data flow, the full query catalog, and gotchas, see
[docs/CODEBASE_MAP.md](docs/CODEBASE_MAP.md).
