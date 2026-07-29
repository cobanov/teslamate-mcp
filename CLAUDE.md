# CLAUDE.md

## Codebase Overview

**teslamate-mcp** is a Model Context Protocol (MCP) server that exposes a TeslaMate PostgreSQL database to AI
assistants over **stdio** and **streamable HTTP**. It surfaces **26 tools** (23 predefined analytics/search
queries defined as `.sql`/`.toml` file pairs with typed optional params + `run_sql` for arbitrary read-only SQL +
`get_database_schema` + `show_charging_curve`, an **MCP Apps** tool that renders an interactive chart
in-conversation and degrades to plain rows on non-Apps clients; +1 opt-in write tool `set_charging_cost` behind
`ENABLE_CHARGING_WRITES`), **prompts**, and **3 resources** (query index, per-query SQL, the `ui://` chart app in
`src/teslamate_mcp/apps/`, wired by `tools/apps_ui.py` via `MCPServer(extensions=[Apps()])`). Built on the official `mcp[cli]` SDK **v2** (`MCPServer`, since 0.6.0), which serves both
protocol eras at once: the stateless **2026-07-28** revision and the legacy `initialize` handshake
(2025-06-18-era clients like the Cloudflare MCP portal). One `psycopg` 3 async pool is owned by the lifespan,
which runs **once per process** on HTTP/stdio (per-session pools leaked connections pre-0.5.1 — don't regress
this; the in-memory test transport re-enters the lifespan per client, so it rebuilds a closed pool on entry).
List endpoints advertise a 1 h `ttl_ms` cache hint (`_CACHE_HINTS` in `server.py`) — the registry is static per
process. Tool handlers log via stdlib `logging`, never `ctx.info()` (the MCP Logging feature is deprecated).

**Stack**: Python 3.11+, `mcp[cli]>=2,<3` (`MCPServer`), psycopg 3 + psycopg-pool, pydantic-settings, click,
Starlette/uvicorn. Hatchling build, ruff, pytest + testcontainers. Ships as a console script and a multi-arch
Docker image on GHCR; the container runs `http --json-response --stateless`.

**Structure**: `src/teslamate_mcp/` is a src-layout package — `cli.py` (entry), `server.py` (MCPServer factory +
lifespan), `db.py` (pool + two trust-level query paths), `tools/` (registry, `run_sql`, schema tool), and
`queries/` (23 bundled `.sql`+`.toml` report pairs). Tests use real Postgres via testcontainers and connect with
the SDK's in-memory `Client` (v2 snake_case result attrs: `is_error`, `structured_content`, `input_schema`).

**Key architectural principle — trust levels**: bundled `.sql` files are trusted and run via the unguarded
`db.fetch_all()`; arbitrary LLM SQL (`run_sql`) runs via `db.fetch_readonly()`, whose Postgres `READ ONLY` +
forced-rollback transaction is the real security boundary (regex validation is only defense-in-depth). The sole
write path is `db.execute_write()`, used only by the opt-in `set_charging_cost` tool
(`ENABLE_CHARGING_WRITES=true`) and bounded by a column-scoped DB grant (`UPDATE (cost) ON charging_processes`).
The declarative registry never writes.

**Add a new tool**: drop a `<name>.sql` + `<name>.toml` (`name`, `description`, optional `[[params]]` tables)
pair into `src/teslamate_mcp/queries/` — auto-discovered and contract-validated on restart, no code change.
Params bind as `%(name)s` placeholders (cast first occurrence; escape literal `%` as `%%`; reserved `%(tz)s`
binds `REPORT_TIMEZONE`).

**Common commands**: `uv sync`, `uv run ruff check/format src tests`, `uv run pytest`,
`uv run teslamate-mcp {stdio|http|gen-token|list-tools}`.

For detailed architecture, data flow, the full query catalog, and gotchas, see
[docs/CODEBASE_MAP.md](docs/CODEBASE_MAP.md).
