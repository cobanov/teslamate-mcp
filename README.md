<div align="center">

# TeslaMate MCP Server

<img src="assets/teslamcp.gif" alt="TeslaMate MCP Server demo" width="720" />

A [Model Context Protocol](https://modelcontextprotocol.io/) server that exposes your [TeslaMate](https://github.com/teslamate-org/teslamate) PostgreSQL database to MCP-aware AI clients (Claude Desktop, Cursor, etc.) over either stdio or streamable HTTP.

[![CI](https://github.com/cobanov/teslamate-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/cobanov/teslamate-mcp/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/cobanov/teslamate-mcp?logo=github&sort=semver)](https://github.com/cobanov/teslamate-mcp/releases)
[![GHCR](https://img.shields.io/badge/ghcr.io-cobanov%2Fteslamate--mcp-2496ED?logo=docker)](https://github.com/cobanov/teslamate-mcp/pkgs/container/teslamate-mcp)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/cobanov/teslamate-mcp)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Archestra Trust Score](https://archestra.ai/mcp-catalog/api/badge/quality/cobanov/teslamate-mcp)](https://archestra.ai/mcp-catalog/cobanov__teslamate-mcp)

</div>

## Features

- **20 tools** — 18 predefined analytics queries (battery, charging, driving, efficiency, locations) plus `run_sql` and `get_database_schema`
- **6 prompts** — one-click workflows for battery health, driving summary, charging behaviour, anomaly hunting, weather efficiency, and a quick status report
- **2 resources** — `teslamate://queries` and `teslamate://queries/{name}` for catalog browsing without invoking a tool
- **Hardened `run_sql`** — runs inside a PostgreSQL `READ ONLY` transaction with `statement_timeout`, `lock_timeout`, and an automatic row cap
- **Live schema introspection** — `get_database_schema` reads `information_schema` at runtime; no stale JSON checked into the repo
- **Two transports, one binary** — `teslamate-mcp stdio` for local clients, `teslamate-mcp http` for remote
- **Bearer-token auth** with timing-safe comparison; `/health` probe for liveness checks
- **`Decimal → float` JSON serialization** so language models see numbers, not strings

## Requirements

- TeslaMate already running against PostgreSQL
- Python 3.11+ for a local install, or Docker for a remote deployment

## Install

```bash
git clone https://github.com/cobanov/teslamate-mcp.git
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
docker run --rm -e DATABASE_URL=... -p 8888:8888 ghcr.io/cobanov/teslamate-mcp:latest
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
| `LOG_LEVEL`             | `INFO`      | Standard Python log level                                   |
| `DEBUG`                 | `false`     | Starlette debug mode (keep off in production)               |

Generate a bearer token:

```bash
uv run teslamate-mcp gen-token
```

## Available tools

### Predefined (18)

**Vehicle:** `get_basic_car_information`, `get_current_car_status`, `get_software_update_history`

**Battery & health:** `get_battery_health_summary`, `get_battery_degradation_over_time`, `get_daily_battery_usage_patterns`, `get_tire_pressure_weekly_trends`

**Driving:** `get_monthly_driving_summary`, `get_daily_driving_patterns`, `get_longest_drives_by_distance`, `get_total_distance_and_efficiency`, `get_drive_summary_per_day`

**Efficiency:** `get_efficiency_by_month_and_temperature`, `get_average_efficiency_by_temperature`, `get_unusual_power_consumption`

**Charging & location:** `get_charging_by_location`, `get_all_charging_sessions_summary`, `get_most_visited_locations`

### Custom (2)

- `get_database_schema` — current TeslaMate schema (one row per column)
- `run_sql(query)` — execute a custom `SELECT` or `WITH … SELECT`

## Adding a new query

1. Drop a SELECT into `src/teslamate_mcp/queries/your_query.sql`.
2. Add a sibling `your_query.toml`:

   ```toml
   name = "get_your_data"
   description = "What this returns."
   ```

3. Restart the server. The registry picks it up automatically.

## Development

```bash
uv sync                          # install with dev deps
uv run ruff check src tests      # lint
uv run ruff format src tests     # format
uv run pytest                    # tests (Docker-backed integration tests skip if Docker is absent)
```

## License

MIT — see [LICENSE](LICENSE).

## Featured in

<a href="https://mseep.ai/app/cobanov-teslamate-mcp">
  <img src="https://mseep.net/pr/cobanov-teslamate-mcp-badge.png" alt="MseeP.ai security audit" width="280" />
</a>
&nbsp;
<a href="https://glama.ai/mcp/servers/@cobanov/teslamate-mcp">
  <img src="https://glama.ai/mcp/servers/@cobanov/teslamate-mcp/badge" alt="Glama MCP catalog" width="280" height="148" />
</a>
