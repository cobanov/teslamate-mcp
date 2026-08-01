# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.1] - 2026-08-01

### Fixed
- **Visible "Resource links are not currently supported" noise in Claude
  Desktop** on every `show_*` app tool result. 0.8.0 prepended a result-level
  `resource_link` block as a second chart-rendering signal; it never triggered
  rendering, and newer Claude Desktop builds surface an unsupported-notice for
  the block instead of silently ignoring it. App tools now rely solely on the
  spec's tool-level `_meta.ui.resourceUri` binding — results are link-free
  again (regression-tested).

## [0.9.0] - 2026-08-01

### Added
- **Seven new analytics queries** (23 → 30 predefined tools):
  - `get_battery_capacity_trend` — usable battery capacity in kWh estimated from
    charging sessions (energy added ÷ SOC gained), monthly per car. A real
    energy-based degradation signal, unlike the rated-range heuristics.
  - `get_vampire_drain` — rated range lost while parked between consecutive
    drives, excluding any gap that contains a charging session.
  - `get_charging_efficiency` — kWh added vs kWh drawn per car, split AC vs DC
    (DC detected via charge samples with no charger phases).
  - `get_charging_by_geofence` — charging totals per TeslaMate geofence
    (Home/Work…), with sessions outside every geofence as "Ungeofenced".
  - `get_soc_hygiene` — share of position samples above 80% / below 20% SOC.
  - `get_period_comparison` — last N days vs the N days before, one row per
    metric across driving and charging, with percent change.
  - `get_drive_route` — NTILE-downsampled GPS track points for one drive.
- **Two new MCP Apps** (`ui://` charts): `show_battery_degradation` (multi-car
  monthly rated-range trend with legend and per-car deltas) and
  `show_drive_route` (pure-SVG route map with start/end markers, scale bar,
  hover readouts). `apps_ui.py` is now spec-driven: app tools are built from a
  declarative `APP_SPECS` tuple via the registry's shared handler factory, so
  an app tool's params, tz injection, and typed output schema can never drift
  from its backing query (this also fixed the app path missing `%(tz)s`
  injection).
- **Confirmation before charging-cost writes**: `set_charging_cost` asks the
  user via MCP elicitation when the client supports it (declarative
  `Resolve`/`Elicit`, which works on the stateless 2026-07-28 transport).
  Clients without form elicitation keep the previous direct-write behavior.
- `get_database_schema(refresh=true)` re-reads `information_schema` on a
  running server; previously DDL changes were only picked up on restart.
- Tests for the previously untested `auth.py`, `prompts.py`, and
  `resources.py`, including a cross-check that every tool name referenced in a
  prompt is a registered tool (renames now fail CI instead of silently
  breaking prompts).

## [0.8.0] - 2026-07-29

### Added
- Typed per-column `outputSchema` for all 23 predefined tools via `[[output]]`
  tables in the `.toml` contract (advisory: nullable fields, extras allowed).
- `ResourceLinkedApps`: UI-bound tool results carry a result-level
  `resource_link` block in addition to tool `_meta.ui`.
- Optional OpenTelemetry export (`telemetry.py`) when
  `OTEL_EXPORTER_OTLP_ENDPOINT` is set; no-op otherwise.

## [0.7.0] - 2026-07-29

### Added
- **MCP Apps pilot**: `show_charging_curve` renders an interactive
  charging-curve chart in-conversation (self-contained `ui://` HTML app,
  ext-apps spec 2026-01-26), degrading to plain rows on non-Apps clients.

## [0.6.1] - 2026-07-29

### Fixed
- Portal sync: serve `/mcp` and `/mcp/` directly (`NormalizeMcpPathMiddleware`)
  instead of 307-redirecting, which broke Cloudflare portal capability sync.

## [0.6.0] - 2026-07-29

### Changed
- Migrated to MCP Python SDK v2 (`MCPServer`, spec 2026-07-28): dual-era
  server (stateless new era + legacy `initialize` handshake), lifespan runs
  once per process and owns the pool, stdlib logging replaces the deprecated
  `ctx.info()`, 1 h `ttl_ms` cache hints on list endpoints, Docker CMD runs
  `--json-response --stateless`.

## [0.5.1] - 2026-07-04

### Fixed
- **Postgres connection exhaustion under real client traffic.** FastMCP runs the lifespan per
  MCP *session*, and the lifespan opened a new connection pool every time; streamable-HTTP
  clients (claude.ai, MCP portals) open sessions freely and rarely terminate them, so pools —
  and their connections — accumulated until Postgres refused new connections
  (`remaining connection slots are reserved…`), which crashed the transport's task group and
  turned every subsequent request into `500: Task group is not initialized`. All sessions now
  share a single pool + schema cache created in `create_server`; the lifespan opens it
  idempotently, never closes it per-session, and never raises (a failed init logs and retries
  on the next session, with individual tool calls surfacing the DB error instead of killing
  the transport). The HTTP app closes the pool on ASGI shutdown.

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
