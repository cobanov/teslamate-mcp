[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/cobanov-teslamate-mcp-badge.png)](https://mseep.ai/app/cobanov-teslamate-mcp)

# TeslaMate MCP Server

[![Trust Score](https://archestra.ai/mcp-catalog/api/badge/quality/cobanov/teslamate-mcp)](https://archestra.ai/mcp-catalog/cobanov__teslamate-mcp)

<a href="https://glama.ai/mcp/servers/@cobanov/teslamate-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@cobanov/teslamate-mcp/badge" alt="teslamate-mcp MCP server" />
</a>

A Model Context Protocol (MCP) server that connects your TeslaMate database to AI assistants, enabling natural language queries about your Tesla data.

## Features

- 🚗 **18 Predefined Queries** - Battery health, efficiency, charging, driving patterns, and more
- 🔍 **Custom SQL Support** - Execute safe SELECT queries with built-in validation
- 🗄️ **Database Schema Access** - Explore your TeslaMate database structure
- 🔒 **Optional Authentication** - Bearer token support for remote deployments
- 🏗️ **Modular Architecture** - Clean, maintainable codebase

## Prerequisites

- [TeslaMate](https://github.com/teslamate-org/teslamate) running with PostgreSQL
- Python 3.11+ (for local) or Docker (for remote)

## Quick Start

### Local Setup (Cursor/Claude Desktop)

```bash
git clone https://github.com/cobanov/teslamate-mcp.git
cd teslamate-mcp
cp env.example .env
# Edit .env with your DATABASE_URL
uv sync
```

Configure your MCP client:

```json
{
  "mcpServers": {
    "teslamate": {
      "command": "uv",
      "args": ["--directory", "/path/to/teslamate-mcp", "run", "main.py"]
    }
  }
}
```

### Remote Setup (Docker)

```bash
git clone https://github.com/cobanov/teslamate-mcp.git
cd teslamate-mcp
cp env.example .env
# Edit .env with your DATABASE_URL
docker-compose up -d
```

Server available at: `http://localhost:8888/mcp`

## Configuration

Create `.env` file:

```env
DATABASE_URL=postgresql://user:pass@host:5432/teslamate
AUTH_TOKEN=                    # Optional: for remote auth
```

**Generate auth token (optional):**

```bash
python utils/generate_token.py
```

## Available Tools

### Predefined Queries (18 tools)

**Vehicle Info:**

- `get_basic_car_information` - VIN, model, firmware
- `get_current_car_status` - Real-time status, location, battery
- `get_software_update_history` - Firmware update timeline

**Battery & Health:**

- `get_battery_health_summary` - Current health metrics
- `get_battery_degradation_over_time` - Historical capacity
- `get_daily_battery_usage_patterns` - Usage patterns
- `get_tire_pressure_weekly_trends` - Tire pressure tracking

**Driving Analytics:**

- `get_monthly_driving_summary` - Monthly statistics
- `get_daily_driving_patterns` - Driving habits
- `get_longest_drives_by_distance` - Top trips
- `get_total_distance_and_efficiency` - Lifetime stats
- `get_drive_summary_per_day` - Daily summaries

**Efficiency:**

- `get_efficiency_by_month_and_temperature` - Seasonal analysis
- `get_average_efficiency_by_temperature` - Temperature impact
- `get_unusual_power_consumption` - Anomaly detection

**Charging & Location:**

- `get_charging_by_location` - Charging patterns
- `get_all_charging_sessions_summary` - Complete history
- `get_most_visited_locations` - Frequent places

### Custom Queries (2 tools)

- `get_database_schema` - View database structure
- `run_sql` - Execute custom SELECT queries (read-only, validated)

## Example Queries

```text
"What's my current battery health?"
"Show me my longest drives"
"How does cold weather affect my efficiency?"
"Where do I charge most often?"
"Run a SQL query to find drives over 100km"
```

## Project Structure

```text
teslamate-mcp/
├── src/              # Core modules
│   ├── config.py     # Configuration
│   ├── database.py    # DB operations
│   ├── tools.py      # Tool registry
│   └── validators.py # SQL validation
├── queries/          # 18 SQL query files
├── data/             # Database schema
├── utils/            # Helper scripts
├── main.py           # Local (STDIO)
├── main_remote.py    # Remote (HTTP)
├── Dockerfile
└── docker-compose.yml
```

## Development

### Adding New Queries

1. Create SQL file in `queries/`:

```sql
-- queries/my_query.sql
SELECT * FROM my_table;
```

2. Add to `src/tools.py`:

```python
ToolDefinition(
    name="get_my_data",
    description="What this returns",
    sql_file="my_query.sql",
)
```

3. Restart server - tool auto-registers!

### Testing

```bash
python test_server.py
```

## Security

- **Authentication**: Optional bearer token for remote access
- **SQL Validation**: Only SELECT queries allowed
- **Read-only**: No data modification possible
- **Use HTTPS**: In production environments

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [TeslaMate](https://github.com/teslamate-org/teslamate) - Tesla data logging
- [Model Context Protocol](https://modelcontextprotocol.io/) - AI integration protocol
