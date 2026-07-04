# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-07-04

### Added
- **Opt-in charging-cost writes**: new `set_charging_cost(charging_process_id, cost)` tool and
  a `backfill_costs_from_receipts` prompt, registered only when `ENABLE_CHARGING_WRITES=true`
  (default off). Designed for the receipt-backfill workflow: match receipts to sessions with
  `search_charging_sessions`, then write each price. Writes go through a dedicated
  `db.execute_write` path (parameterized UPDATE ... RETURNING, committed); the recommended
  database boundary is a column-scoped grant — `GRANT UPDATE (cost) ON charging_processes TO
  <role>;` — so nothing outside that single column can ever be modified, regardless of code.
  `run_sql` remains READ ONLY + forced rollback; the declarative query registry remains
  read-only by design. Tests cover flag gating, the end-to-end write, and prove the
  column-scoped grant blocks writes to other columns.

## [0.4.0] - 2026-07-04

### Added
- **Typed tool parameters**: the `.toml` sidecar contract now supports `[[params]]` tables
  (name, type, description, required, default, minimum/maximum, enum). Declared params are
  validated at startup, surfaced in each tool's MCP input schema with types/defaults/constraints,
  and bound to `%(name)s` placeholders via psycopg — never interpolated into SQL text.
- All 18 predefined queries now accept optional filters (`car_name` everywhere; `days` windows;
  `limit`, and per-tool thresholds like `min_swing_pct`/`threshold_pct`). Zero-argument calls
  return exactly what they returned before — defaults mirror the old hardcoded values.
- **Five new tools**: `search_drives` (date range, location text, distance bounds, sort),
  `search_charging_sessions`, `get_drive_details(drive_id)`, `get_charging_curve
  (charging_process_id)` (NTILE-downsampled curve from the `charges` table), and
  `get_charging_costs` (group by month/location/car).
- `REPORT_TIMEZONE` setting (IANA name, default `UTC`): daily/weekly/monthly buckets in the
  reporting queries are computed in this timezone via `AT TIME ZONE` binding.
- `get_database_schema` now takes an optional `table` argument: omit it for a compact
  table list with column counts, pass a table name for full column detail.
- Discovery-time SQL lint: undeclared/unused placeholders and unescaped literal `%` in
  parameterized queries fail fast at startup.
- Test suite: TOML contract validation tests, generated-schema assertions, and an end-to-end
  suite that runs every bundled tool against a seeded TeslaMate-shaped Postgres (testcontainers),
  including timezone bucketing and param binding.

### Changed
- All tool descriptions rewritten to be accurate and information-dense (units, grouping,
  default windows, available filters). Three descriptions that claimed per-car grouping for
  fleet-wide aggregates (`get_drive_summary_per_day`, `get_charging_by_location`,
  `get_most_visited_locations`) are corrected.
- `fetch_all` accepts dict params for named-placeholder binding.
- `list-tools` prints each tool's parameter names.
- The `teslamate://queries` resource index includes each query's param names.

### Fixed
- `get_battery_health_summary` failed at runtime with `function round(double precision, integer)
  does not exist` — the health percentage expression lacked a `::numeric` cast. Caught by the
  new run-every-tool e2e test.

## [0.3.1] - 2026-05-21

### Fixed
- FastMCP exposed the internal `Context` parameter (`ctx`) as a required client-facing tool argument on every tool, so MCP clients failed every call with `ctx Field required`. `from __future__ import annotations` made FastMCP see the annotation as a string and miss the Context-detection branch; the fix patches `__annotations__["ctx"]` back to the real `Context` class before registering each tool. ([#7](https://github.com/cobanov/teslamate-mcp/pull/7))

### Added
- Regression test that constructs the server and asserts `ctx` is absent from every tool's MCP-facing `inputSchema` while `run_sql` still requires `query`.

## [0.3.0] - 2026-05-21

### Added
- Single `teslamate-mcp` console script with `stdio`, `http`, `gen-token`, and `list-tools` subcommands.
- `src/teslamate_mcp` package using a proper src-layout, distributable via hatchling.
- Six MCP prompts for common analyses: battery health, driving summary, charging behaviour, anomalies, weather efficiency, and a quick status report.
- Two MCP resources: `teslamate://queries` (index) and `teslamate://queries/{name}` (raw SQL per tool).
- `Context.info`/`Context.warning` streaming from every tool, including elapsed time on `run_sql`.
- `/health` liveness route and Docker `HEALTHCHECK`.
- Multi-stage Dockerfile producing a slim runtime image with OCI labels.
- Release workflow: pushing a `v*` tag builds and publishes a multi-arch image to GHCR and opens a GitHub release.
- GitHub Actions CI: ruff lint/format check, pytest on Python 3.11/3.12/3.13, Docker build smoke test.
- pytest suite with testcontainers-backed Postgres for end-to-end coverage of the read-only execution path.

### Changed
- `run_sql` now runs inside a PostgreSQL `READ ONLY` transaction with `statement_timeout`, `lock_timeout`, and `idle_in_transaction_session_timeout` enforced via `SET LOCAL`. When the user omits `LIMIT`, the query is wrapped in a capped subselect.
- `get_database_schema` reads `information_schema` at runtime instead of a checked-in JSON snapshot.
- Decimal column values are serialised as `float` so language models can do arithmetic on them.
- Bearer-token comparison switched to `hmac.compare_digest` (timing-safe).
- Configuration moved to `pydantic-settings` with full `.env` support.

### Removed
- `main.py` and `main_remote.py` (replaced by the CLI subcommands).
- `utils/generate_token.py` (replaced by `teslamate-mcp gen-token`).
- `data/all_db_info.json` (replaced by live introspection).
- Direct dependency on the standalone `fastmcp` PyPI package; the project now uses only the official `mcp[cli]` SDK.

## [0.2.0]

Previous baseline. See git history for details.
