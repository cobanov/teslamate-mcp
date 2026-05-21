# TeslaMate MCP Server

![TeslaMate MCP Server](assets/teslamcp.gif)

[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/cobanov-teslamate-mcp-badge.png)](https://mseep.ai/app/cobanov-teslamate-mcp)
[![Trust Score](https://archestra.ai/mcp-catalog/api/badge/quality/cobanov/teslamate-mcp)](https://archestra.ai/mcp-catalog/cobanov__teslamate-mcp)

<a href="https://glama.ai/mcp/servers/@cobanov/teslamate-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@cobanov/teslamate-mcp/badge" alt="teslamate-mcp MCP server" />
</a>

A [Model Context Protocol](https://modelcontextprotocol.io/) server that exposes your [TeslaMate](https://github.com/teslamate-org/teslamate) PostgreSQL database to MCP-aware AI clients (Claude Desktop, Cursor, etc.) over either stdio or streamable HTTP.

## Features

- **18 predefined analytics queries** — battery health, charging, driving patterns, efficiency, locations, more
- **Custom read-only SQL** — `run_sql` runs inside a PostgreSQL `READ ONLY` transaction with `statement_timeout`, `lock_timeout`, and an automatic row cap
- **Live schema introspection** — `get_database_schema` reads `information_schema` at runtime, no stale JSON
- **Two transports, one binary** — `teslamate-mcp stdio` for local clients, `teslamate-mcp http` for remote
- **Bearer-token auth** with timing-safe comparison for the HTTP transport
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

The server listens on `http://localhost:8888/mcp`.

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

## Custom SQL safety model

`run_sql` does **not** rely on a regex blacklist alone. The actual guarantees come from the database:

1. **Regex pre-check** rejects multi-statement input and non-`SELECT`/`WITH` leading keywords (cheap fail-fast).
2. **PostgreSQL `READ ONLY` transaction** with `SET LOCAL statement_timeout`, `lock_timeout`, and `idle_in_transaction_session_timeout`. The transaction is rolled back unconditionally.
3. **Automatic LIMIT** — if you omit `LIMIT`, your query is wrapped in `SELECT * FROM (<your query>) AS _capped LIMIT 1000`.
4. **Recommended**: connect with a dedicated read-only PostgreSQL role for defense in depth.

## Project layout

```text
teslamate-mcp/
├── src/teslamate_mcp/
│   ├── cli.py            # click subcommands
│   ├── server.py         # FastMCP factory + lifespan
│   ├── config.py         # pydantic-settings
│   ├── db.py             # async pool + read-only helper
│   ├── auth.py           # bearer middleware
│   ├── schema.py         # information_schema introspection
│   ├── serialization.py  # Decimal/datetime → JSON
│   ├── tools/
│   │   ├── registry.py     # discover .sql + .toml pairs
│   │   ├── custom_sql.py   # run_sql
│   │   └── schema_tool.py  # get_database_schema
│   └── queries/          # 18 .sql files, each with a sibling .toml
├── tests/                # pytest, testcontainers-postgres
├── Dockerfile            # multi-stage
└── docker-compose.yml
```

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
