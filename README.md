<div align="center">

# TeslaMate MCP Server

<img src="assets/teslamcp.gif" alt="TeslaMate MCP Server demo" width="720" />

A [Model Context Protocol](https://modelcontextprotocol.io/) server that exposes your [TeslaMate](https://github.com/teslamate-org/teslamate) PostgreSQL database to MCP-aware AI clients (Claude Desktop, Cursor, etc.) over either stdio or streamable HTTP.

[![CI](https://github.com/batubozkan/teslamate-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/batubozkan/teslamate-mcp/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/batubozkan/teslamate-mcp?logo=github&sort=semver)](https://github.com/batubozkan/teslamate-mcp/releases)
[![GHCR](https://img.shields.io/badge/ghcr.io-batubozkan%2Fteslamate--mcp-2496ED?logo=docker)](https://github.com/batubozkan/teslamate-mcp/pkgs/container/teslamate-mcp)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/batubozkan/teslamate-mcp)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Fork of [cobanov/teslamate-mcp](https://github.com/cobanov/teslamate-mcp) carrying the 0.4.0+ feature line: typed tool parameters & outputs, 12 additional analytics/search tools, MCP SDK v2 (spec 2026-07-28), interactive MCP Apps charts, opt-in charging-cost writes with elicitation confirm, and OpenTelemetry export.

</div>

## Features

- **35 tools** — 30 predefined analytics & search queries (battery capacity & degradation, vampire drain, charging efficiency & costs, geofences, driving, efficiency, locations, routes, search and detail) plus `run_sql`, `get_database_schema`, and 3 MCP Apps chart tools
- **MCP Apps** — `show_charging_curve`, `show_battery_degradation`, and `show_drive_route` render interactive charts directly in the conversation on Apps-capable clients, and degrade to plain data everywhere else
- **Typed tool parameters & outputs** — every predefined tool accepts optional filters (`car_name`, `days` windows, `limit`, thresholds) declared in its `.toml` sidecar, validated at startup, and bound safely via psycopg named params; `[[output]]` declarations give each tool a typed per-column `outputSchema`. Zero-argument calls return the full classic report
- **Timezone-aware reports** — set `REPORT_TIMEZONE` (IANA name) so daily/weekly/monthly buckets follow your local midnight instead of UTC
- **6 prompts** — one-click workflows for battery health, driving summary, charging behaviour, anomaly hunting, weather efficiency, and a quick status report
- **Resources** — `teslamate://queries` and `teslamate://queries/{name}` for catalog browsing, plus the `ui://` chart apps
- **Hardened `run_sql`** — runs inside a PostgreSQL `READ ONLY` transaction with `statement_timeout`, `lock_timeout`, and an automatic row cap
- **Live schema introspection** — `get_database_schema` lists all tables compactly, full column detail for one `table`, and re-reads the schema on demand with `refresh=true`
- **Two transports, one binary** — `teslamate-mcp stdio` for local clients, `teslamate-mcp http` for remote
- **Bearer-token auth** with timing-safe comparison; `/health` probe for liveness checks
- **`Decimal → float` JSON serialization** so language models see numbers, not strings

## Requirements

- TeslaMate already running against PostgreSQL
- Python 3.11+ for a local install, or Docker for a remote deployment

## Install

```bash
git clone https://github.com/batubozkan/teslamate-mcp.git
cd teslamate-mcp
cp env.example .env
# Edit .env — at minimum, set DATABASE_URL
uv sync
```

## CLI

The `teslamate-mcp` console script has four subcommands:

```bash
teslamate-mcp stdio                          # local (Cursor / Claude Desktop)
teslamate-mcp http [--host] [--port]         # remote (HTTP / SSE)
teslamate-mcp gen-token                      # produce an AUTH_TOKEN value
teslamate-mcp list-tools                     # diagnostic: list registered tools
```

`python -m teslamate_mcp <subcommand>` works too.

## Local use (stdio)

Configure your MCP client to launch the stdio server. Example for Cursor or Claude Desktop:

```json
{
  "mcpServers": {
    "teslamate": {
      "command": "uv",
      "args": ["--directory", "/path/to/teslamate-mcp", "run", "teslamate-mcp", "stdio"]
    }
  }
}
```

## Remote use (Docker)

```bash
cp env.example .env
# Set DATABASE_URL and ideally AUTH_TOKEN
docker compose up -d
```

The MCP endpoint is at `http://localhost:8888/mcp` and a liveness probe is exposed at `http://localhost:8888/health`.

A prebuilt multi-arch image (`linux/amd64`, `linux/arm64`) is also published to GHCR on every tagged release:

```bash
docker run --rm -e DATABASE_URL=... -p 8888:8888 ghcr.io/batubozkan/teslamate-mcp:latest
```

## Configuration

All settings are read from environment variables (`.env` supported). Only `DATABASE_URL` is required.

| Variable                | Default     | Notes                                                       |
|-------------------------|-------------|-------------------------------------------------------------|
| `DATABASE_URL`          | _required_  | `postgresql://user:pass@host:5432/teslamate`                |
| `AUTH_TOKEN`            | _empty_     | Enables bearer auth on the HTTP endpoint                    |
| `HOST`                  | `0.0.0.0`   | HTTP bind host                                              |
| `PORT`                  | `8888`      | HTTP bind port                                              |
| `POOL_MIN_SIZE`         | `1`         | psycopg pool floor                                          |
| `POOL_MAX_SIZE`         | `10`        | psycopg pool ceiling                                        |
| `QUERY_TIMEOUT_MS`      | `5000`      | `statement_timeout` for `run_sql`                           |
| `CUSTOM_SQL_ROW_LIMIT`  | `1000`      | LIMIT injected when `run_sql` doesn't supply one            |
| `REPORT_TIMEZONE`       | `UTC`       | IANA timezone for daily/weekly/monthly report buckets       |
| `ENABLE_CHARGING_WRITES`| `false`     | Register `set_charging_cost` (needs the UPDATE(cost) grant) |
| `LOG_LEVEL`             | `INFO`      | Standard Python log level                                   |
| `DEBUG`                 | `false`     | Starlette debug mode (keep off in production)               |

Generate a bearer token:

```bash
uv run teslamate-mcp gen-token
```

## Available tools

Every predefined tool accepts **optional filters** — `car_name` (substring match) everywhere,
plus `days` windows, `limit` caps, and per-tool thresholds where they make sense. Calling a
tool with no arguments returns the full classic report.

### Predefined reports (18)

**Vehicle:** `get_basic_car_information`, `get_current_car_status`, `get_software_update_history`

**Battery & health:** `get_battery_health_summary`, `get_battery_degradation_over_time`, `get_daily_battery_usage_patterns`, `get_tire_pressure_weekly_trends`

**Driving:** `get_monthly_driving_summary`, `get_daily_driving_patterns`, `get_longest_drives_by_distance`, `get_total_distance_and_efficiency`, `get_drive_summary_per_day`

**Efficiency:** `get_efficiency_by_month_and_temperature`, `get_average_efficiency_by_temperature`, `get_unusual_power_consumption`

**Charging & location:** `get_charging_by_location`, `get_all_charging_sessions_summary`, `get_most_visited_locations`

### Insights (6)

- `get_battery_capacity_trend` — usable battery capacity (kWh) estimated from charging sessions (energy added ÷ SOC gained), monthly per car — a real energy-based degradation signal
- `get_vampire_drain` — rated range lost while parked between drives, excluding gaps that contain a charge
- `get_charging_efficiency` — kWh added vs kWh drawn per car, split AC vs DC
- `get_charging_by_geofence` — charging totals per TeslaMate geofence (Home/Work/…) plus "Ungeofenced"
- `get_soc_hygiene` — share of samples above 80% / below 20% SOC (battery-care habits)
- `get_period_comparison` — last N days vs the N days before, one row per driving/charging metric

### Search & detail (6)

- `search_drives` — filter drives by date range, location text, distance bounds, car; sortable
- `search_charging_sessions` — filter charging sessions by date range, location, energy, car
- `get_drive_details(drive_id)` — full stats for one drive found via search
- `get_drive_route(drive_id)` — downsampled GPS track points for one drive
- `get_charging_curve(charging_process_id)` — downsampled power/SOC curve for one session
- `get_charging_costs` — cost breakdown grouped by month, location, or car

### MCP Apps (3)

`show_charging_curve`, `show_battery_degradation`, and `show_drive_route` are the interactive
counterparts of `get_charging_curve`, `get_battery_degradation_over_time`, and
`get_drive_route`: on Apps-capable clients they render a self-contained chart (charging curve,
degradation trend, route map) inline in the conversation; on every other client they return
exactly the same rows as their backing query tool.

### Custom (2)

- `get_database_schema([table], [refresh])` — compact table list, full column detail for one table, or a forced re-read after DDL changes
- `run_sql(query)` — execute a custom `SELECT` or `WITH … SELECT`

### Write tools (opt-in, off by default)

Set `ENABLE_CHARGING_WRITES=true` to register **`set_charging_cost(charging_process_id, cost)`**
— sets the total cost of one charging session (the same field TeslaMate's UI edits), plus a
`backfill_costs_from_receipts` prompt that guides the receipt→session matching workflow.
On clients that support MCP elicitation the user is shown a confirmation dialog before each
write; clients without it proceed directly (unchanged behavior).

Grant the database role write access to **that single column only** (the real security
boundary — nothing else can ever be written):

```sql
GRANT UPDATE (cost) ON charging_processes TO teslamate_ro;
```

`run_sql` stays read-only regardless (READ ONLY transaction + forced rollback), and the
declarative query registry never writes.

## Adding a new query

1. Drop a SELECT into `src/teslamate_mcp/queries/your_query.sql`.
2. Add a sibling `your_query.toml`:

   ```toml
   name = "get_your_data"
   description = "What this returns, units, grouping, and available filters."

   [[params]]                 # optional — declare typed tool arguments
   name = "car_name"
   type = "string"            # string | integer | number | boolean
   description = "Case-insensitive substring match on the car's name."

   [[params]]
   name = "limit"
   type = "integer"
   description = "Maximum number of rows returned."
   default = 10
   minimum = 1
   maximum = 100

   [[output]]                 # optional — one table per result column for a typed outputSchema
   name = "car_name"
   type = "string"
   ```

3. Reference params in the SQL as `%(car_name)s` placeholders — **never** string-interpolate.
   Rules enforced at startup: every declared param must appear in the SQL (and vice versa);
   cast the first occurrence (`%(car_name)s::text`, `%(limit)s::int`) so NULL binding works;
   escape literal `%` as `%%` in parameterized queries. The reserved `%(tz)s` placeholder binds
   `REPORT_TIMEZONE` automatically for `AT TIME ZONE` bucketing.
4. Restart the server. The registry validates and picks it up automatically
   (`teslamate-mcp list-tools` to confirm).

## Development

```bash
uv sync                          # install with dev deps
uv run ruff check src tests      # lint
uv run ruff format src tests     # format
uv run pytest                    # tests (Docker-backed integration tests skip if Docker is absent)
```

## License

MIT — see [LICENSE](LICENSE). Based on [cobanov/teslamate-mcp](https://github.com/cobanov/teslamate-mcp) by Mert Cobanov.
