# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Climate run while parked**, from the climate state TeslaMate records in
  its polled samples.
  - `get_parked_climate_sessions`: each time the climate ran while parked
    (preconditioning before a drive, cooling down after arriving, Keep
    Climate / Dog / Camp mode), with minutes, estimated battery kWh, cooling
    or heating, temperatures, set temperature, and where. Each sample stands
    for the time until the next one, capped at 10 minutes and at the next
    drive's start; plugged-in time counts toward duration but not battery
    energy.
  - `get_climate_usage`: the same per month, with the preconditioning count,
    hours plugged in, and the energy's estimated cost at that month's average
    recorded price.
- **A year or month in review.** `get_recap` / `show_recap` (a new chart):
  totals, the distance against the period before (cut at the same point while
  the period is still running, so a year in progress is not measured against
  a whole year), charging and cost, and highlights: the longest drive and
  where it went, the busiest day, the most efficient day or month, the
  favourite destination and charging spot, top speed, the temperature range,
  and software updates. Defaults to the current year; `period='month'` for a
  month.
- `year_in_review` prompt; `monthly_recap` now starts from `show_recap` and
  adds the climate used while parked.

## [0.13.5] - 2026-09-30

### Added
- **Sleep and wake analysis** from TeslaMate's `states` table, which no tool
  read before.
  - `get_state_history`: per car and local day, hours online, asleep and
    offline, driving and charging hours, idle awake hours (online while parked
    and not charging, the time that drains the battery), wake-ups, and the
    share of the day asleep or offline. Intervals are split at local midnight.
  - `get_idle_awake_periods`: the online periods that kept the car awake while
    parked, longest idle time first, with where the car was parked.
  - `get_current_car_status` now reports `car_state` (driving, charging,
    online, asleep, or offline) and `car_state_since`.
  An online state that TeslaMate never closed (it loses contact with a car
  whose API token was revoked or that was sold) ends at the car's last logged
  position instead of running to now, and drives TeslaMate left open after a
  restart count neither as driving time nor as "driving now".
- **`get_timeline`**: what the car did, in order — drives, charging sessions,
  the time parked between them (with the share spent asleep or offline), and
  software updates — with local times, places (geofence names first), battery
  % at each end, kWh and cost. Defaults to the last 7 local days; a date range
  shows any day. Parks are the gaps between activities, worked out over the
  car's whole history, so a range never cuts a park short.
- **`get_trip_energy_estimate`** ("will I make it?"): energy and battery % a
  drive of a given distance will take, learned from the car's own drives at a
  similar outside temperature (within 3°C, widening until there is enough
  history), optionally motorway drives only. Returns expected and
  conservative (90th percentile) consumption, usable capacity, full-battery
  range, and the arrival battery % from the latest recorded level or a given
  one. Consumption and capacity both come from the rated-range scale, so they
  stay consistent with each other.
- **`get_charging_cost_estimates`**: an estimated cost for every charging
  session with none recorded, from the first basis that applies: free
  Supercharging, a `price_per_kwh` argument, the session's geofence tariff,
  the median price paid at the same address (nearest sessions in time), or
  the median price for the same charger type (Supercharger, other DC, AC).
  Pairs with `set_charging_cost` to backfill.
- **`get_fuel_savings`**: the fuel the same distance would have taken and
  cost, against what charging cost, with a coverage figure when some sessions
  have no cost (or an `electricity_price_per_kwh` to price them).
- `get_charging_costs` and `get_charging_by_geofence` report
  `sessions_without_cost`.
- **Fast-charging analytics** from the charges' fast-charger fields, which no
  tool read before.
  - `get_fast_charging_sessions`: DC sessions with charger type (Supercharger
    or third-party), connector, peak and average power, average power across
    20–80%, minutes from 20% to 80%, whether the battery heater ran, and cost.
  - `get_fast_charging_by_location`: the same per location and charger type,
    with the price paid per kWh.
  - `get_charging_curve_comparison` and the `show_charging_curve_comparison`
    MCP App: several sessions' power against battery %, overlaid, so a slow
    session can be told apart from a cold or full battery.
- **Elevation**, which TeslaMate records but no tool read.
  - `get_efficiency_by_elevation`: consumption by net climb per km (downhill
    to uphill), per car, against the car's flat drives. Net climb (ascent
    minus descent) because GPS noise inflates ascent and descent alike.
  - `get_drive_details` and `get_trips` report `ascent_m` and `descent_m`;
    `get_drive_route` and `get_trip_route` report `elevation_m` per point.
  - `show_drive_route` and `show_trip_route` draw an elevation profile under
    the map, linked to it on hover.
- **Three more charts**, each the MCP App of a new report:
  - `show_activity_report` / `get_activity_report`: a month by day or a year
    by month (distance, drives, consumption, kWh charged, cost, temperature),
    with totals and empty days kept.
  - `show_visited_places` / `get_visited_places`: a map of where the car
    parks, sized by arrivals, with hours parked and charging per place.
  - `show_efficiency_vs_temperature` / `get_drive_efficiency_points`: every
    drive's consumption against outside temperature, sized by distance, with
    the distance-weighted 5 °C average and the cold-weather penalty.

- **`get_unit_preferences`**: the units chosen in TeslaMate's settings
  (length, temperature, pressure, rated or ideal range), with the conversion
  factors in its description, so the assistant answers in miles, °F, or psi
  where the user asked TeslaMate for them. Tools keep returning metric values
  and rated range; the charts stay metric.

- **Server instructions.** The server now sends MCP `instructions`: units
  and rated range, UTC timestamps against the configured `REPORT_TIMEZONE`,
  unknown costs, and a short map from kind of question to tool (trips vs
  drives, sleep, range planning, charging, costs, overviews, charts vs their
  data twins). `set_charging_cost` is mentioned only when writes are enabled;
  a test keeps every tool it names registered.

- **Five new prompts**: `diagnose_sleep`, `plan_trip` (destination and
  temperature arguments), `review_trip`, `monthly_recap`, and
  `charging_costs_and_savings`.

### Changed
- **Prompts use the newer tools.** `analyze_battery_health` starts from the
  energy-based capacity trend and looks at charging habits, `analyze_charging`
  fills in missing costs and compares fast chargers, `find_anomalies` checks
  sleep and hills, `summarize_driving` reports journeys, and
  `weather_efficiency` plots every drive. `status_report` no longer asks for
  a pending software update, which TeslaMate does not record, and says when
  TeslaMate has lost contact with the car. `backfill_costs_from_receipts`
  offers estimates for sessions without a receipt.
- The README, Unraid template, `env.example`, and CONTRIBUTING.md match the
  current tools, prompts, and charts (the README still said 30 report tools
  and 3 charts), `MAP_TILES` is described as covering every map, and the
  package URLs point to this fork, with the upstream project listed.
- `get_most_visited_locations` documents `total_time_spent_min` as what it
  is, the driving time of drives starting or ending there, not time parked
  (`get_visited_places` has that).

### Fixed
- **`run_sql`'s row cap could be bypassed** (a known limitation in
  SECURITY.md): the query was wrapped in `LIMIT` only when it had no `LIMIT`
  of its own, so `SELECT * FROM (SELECT … LIMIT 5000000) x` ran uncapped.
  The query now runs through a server-side cursor and at most
  `CUSTOM_SQL_ROW_LIMIT` rows are fetched, whatever it says; the rest never
  leave PostgreSQL. The tool description states the cap.
- **`get_charging_efficiency` counted many AC sessions as DC.** A session was
  DC when any sample had no charger phases, but AC sessions often end on a
  0 kW sample with no phases (39 of 218 sessions on a real database). DC now
  needs a sample from a fast charger, or one with no phases while power
  flowed; every tool that splits AC from DC uses that same test.
- **Average cost per kWh was too low whenever some sessions had no cost.**
  `get_charging_costs` and `get_charging_by_geofence` divided the recorded
  costs by the energy of every session, so each session with no cost counted
  as free charging. The average now covers only sessions that have a cost.

## [0.13.0] - 2026-09-30

### Added
- **Trips.** TeslaMate ends a drive every time the car parks, so one journey
  with a WC break and a charging stop is several drives. Three new tools
  merge a car's consecutive drives while each stop in between stays short:
  up to `max_stop_minutes` (default 30) without charging, or
  `max_charging_stop_minutes` (default 120) when a charging session happened
  during the stop.
  - `get_trips`: one row per trip with legs, stops and charging stops,
    distance, driving/stopped/total time, moving speed, battery % at start
    and end, kWh added on the way, rated range used, and average outside
    temperature. Filters: dates, car, distance, number of legs, and a place
    the trip passed through (any leg's start or end, not only the endpoints).
  - `get_trip_details`: one trip's timeline of drives and stops, with where
    and how long each stop lasted and, for charging stops, kWh added and
    battery % before and after.
  - `get_trip_route` and the `show_trip_route` MCP App: the whole trip on the
    basemap, with a marker at every stop and charging stops highlighted.
  All three share one grouping block (a test keeps the copies identical), and
  `trip_id` is the trip's first drive id; any drive id in the trip also works.
  Unlike Grafana's Continuous Trips dashboard, which splits at every charge,
  a charging stop on the way stays part of the trip.

### Changed
- Tests can run against an existing PostgreSQL via
  `TESLAMATE_TEST_DATABASE_URL` instead of Docker (point it at a scratch
  database; the seed drops and recreates its tables).

## [0.12.0] - 2026-09-30

### Added
- **Basemap under the route map.** `show_drive_route` now draws the track over
  a low-detail basemap: Esri's gray canvas base layer, light or dark to match
  the client, with the required attribution. The route is projected in Web
  Mercator so it lines up with the tiles, gets a halo for contrast, and the
  scale bar accounts for latitude. The view declares the tile host in
  `_meta.ui.csp.resourceDomains`; if tiles fail to load, the plain route still
  draws.
- `MAP_TILES` setting (default `true`). Tiles are fetched by the viewer's
  browser, which tells Esri the rough area being viewed; `MAP_TILES=false`
  keeps the view fully self-contained. The setting is part of the view's URI
  fingerprint, so toggling it never reuses a host's cached copy.

## [0.11.3] - 2026-09-30

### Fixed
- **Hosts could keep running a stale chart view after an upgrade.** View URIs
  never changed between releases, and after upgrading to 0.11.2 claude.ai's
  frame still ran a view without the fixed handshake. Views are now served at
  `ui://teslamate/<content-hash>/<name>.html`, so any change to a view gets a
  new URI while unchanged views stay cacheable.
- **Charts showed "no data" when the host omitted `structuredContent`.** The
  views now fall back to the rows in the result's text blocks.

## [0.11.2] - 2026-09-30

### Fixed
- **MCP Apps charts opened but stayed empty.** The chart views sent
  `clientInfo` in `ui/initialize`, but `McpUiInitializeRequest` (ext-apps
  2026-01-26) requires `appInfo`, `appCapabilities` and `protocolVersion`, and
  hosts validate it. The host rejected the handshake, the view swallowed the
  error and never sent `ui/notifications/initialized`, and hosts deliver
  `tool-input`/`tool-result` only after that notification. All three views now
  send the spec's fields, answer the host's `ping`, reply `Method not found` to
  other host requests instead of leaving them to time out, and show an error
  state when the handshake is rejected.

## [0.11.1] - 2026-09-30

### Fixed
- **MCP Apps charts could still fall back to plain rows.** App tools now carry
  the deprecated flat `_meta["ui/resourceUri"]` key alongside
  `_meta.ui.resourceUri`, matching the ext-apps reference SDK
  (`registerAppTool`), which stamps both because hosts that predate the nested
  form only read the flat one. The Python SDK's `Apps.tool()` writes only the
  nested form.

## [0.11.0] - 2026-09-30

### Added
- **Cloudflare Access authentication.** With `CF_ACCESS_TEAM_DOMAIN` and
  `CF_ACCESS_AUD` set, the HTTP transport also accepts requests carrying a
  verified `Cf-Access-Jwt-Assertion` (RS256 signature against the team's
  published keys, issuer, audience, expiry; keys cached and refetched on
  rotation). `AUTH_TOKEN` keeps working alongside it. This lets claude.ai
  connect through an Access application with Managed OAuth directly, instead
  of through the MCP Server Portal, which namespaces `ui://` resource URIs
  (`teslamate-mcp_ui://...`) and so prevents the `show_*` charts from rendering.
- `pyjwt[crypto]` is now a direct dependency (it was already installed
  transitively through `mcp`).

## [0.10.1] - 2026-08-03

### Fixed
- **`/health` could return 500 instead of 503.** The 0.10.0 probe took the
  first line of `str(exc)` to build its `detail` field, but an empty message
  has no lines at all — and `asyncio.timeout` raises exactly that, a bare
  `TimeoutError`. So the most likely failure the probe exists to report, a
  database too slow to answer within 3s, crashed the probe instead of
  reporting `degraded`. Regression-tested.

### Changed
- **`env.example` now defaults to a read-only role.** TeslaMate's own Compose
  sets `POSTGRES_USER=teslamate`, making that role a superuser. Pointing
  `DATABASE_URL` at it leaves every write blocked but still permits
  superuser-only *read* functions through `run_sql` — `pg_read_file`,
  `pg_ls_dir`, `pg_authid`. `SECURITY.md` now documents this explicitly, with
  the `CREATE ROLE` snippet and two other known limitations (the row cap is
  bypassable by a nested `LIMIT`; `/health` is unauthenticated by design).
- Added `deploy/unraid/README.md`, a short index for the Community
  Applications template and the
  [Unraid + Cloudflare walkthrough](deploy/unraid/UNRAID_CLOUDFLARE_DEPLOYMENT.md),
  which stays in this repository.

## [0.10.0] - 2026-08-02

### Fixed
- **`get_battery_health_summary` and `get_current_car_status` never returned on
  a large database.** Both selected the newest position per car with a
  correlated subquery — `WHERE p.date = (SELECT MAX(date) FROM positions p2
  WHERE p2.car_id = p.car_id)` — which re-scans the whole `positions` table
  once per candidate row. On a 3.1M-row table PostgreSQL costed the plan at
  ~2.6e11 and it never completed. Both now take the latest position through a
  `LATERAL` top-1 driven from `cars`, which also lets the `car_name` filter cut
  the set before any positions lookup: 0.9s and 1.1s respectively on the same
  database, against no result at all before.
- **A slow query could pin a PostgreSQL backend indefinitely.** The predefined
  query path (`fetch_all`) set no `statement_timeout`, so a pathological query
  hung the MCP client with no error while the server kept burning CPU — and
  killing the client did not cancel the server-side query. The pool now sets a
  connection-level `statement_timeout` bounding every query it runs, tunable
  with the new `STATEMENT_TIMEOUT_MS` (default 30s) and skipped when
  `DATABASE_URL` carries its own libpq `options=`.
- **`/health` reported `ok` while the server could not serve at all.** The
  probe never touched the database, so a container whose pool could not reach
  PostgreSQL — every MCP call returning 500 — was still marked healthy by the
  Docker `HEALTHCHECK`. It now performs a real `SELECT 1` (3s cap) and returns
  `503` with `{"status": "degraded", "database": "unreachable", "detail": …}`
  when that fails.

### Added
- `STATEMENT_TIMEOUT_MS` setting (default `30000`).
- `/health` now reports a `database` field alongside `status` and `version`.

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
