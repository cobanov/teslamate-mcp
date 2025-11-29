# TeslaMate MCP Server

A Model Context Protocol (MCP) server that provides access to your TeslaMate database, allowing AI assistants to query Tesla vehicle data and analytics.

![teslamate-mcp](assets/teslamcp.gif)

## Overview

This MCP server connects to your TeslaMate PostgreSQL database and exposes various tools to retrieve Tesla vehicle information, driving statistics, charging data, battery health, efficiency metrics, and location analytics. It's designed to work with MCP-compatible AI assistants like Claude Desktop and Cursor IDE, enabling natural language queries about your Tesla data.

## Features

- 🚗 **18 Predefined Queries** - Battery health, efficiency, charging, driving patterns, and more
- 🔍 **Custom SQL Support** - Execute safe SELECT queries with built-in validation
- 🗄️ **Database Schema Access** - Explore your TeslaMate database structure
- 🔒 **Bearer Token Authentication** - Optional secure access control
- 🌐 **Dual Transport Modes** - Local (stdio) and remote (HTTP) connections
- 🏗️ **Modular Architecture** - Clean, maintainable, and extensible code structure

## Project Structure

```
teslamate-mcp/
├── src/
│   ├── config.py          # Configuration
│   ├── database.py        # DB operations
│   ├── tools.py           # Tool registry
│   └── validators.py       # SQL validation
│       ├── __init__.py          # Package initialization
│       ├── config.py            # Configuration management
│       ├── database.py          # Database operations
│       ├── tools.py             # Tool definitions
│       └── validators.py        # SQL validation utilities
├── queries/                     # SQL query files (18 files)
├── data/                        # Data files
│   └── all_db_info.json        # Database schema information
├── utils/                       # Utility scripts
│   └── generate_token.py       # Bearer token generator
├── main.py                      # STDIO transport (local)
├── main_remote.py               # HTTP transport (remote)
├── test_server.py               # Test script
├── Dockerfile                   # Docker image definition
├── docker-compose.yml           # Docker deployment config
├── pyproject.toml              # Project metadata
├── env.example                 # Environment variables template
└── README.md                   # This file
```

## Prerequisites

- [TeslaMate](https://github.com/teslamate-org/teslamate) running with a PostgreSQL database
- Python 3.11 or higher
- Access to your TeslaMate database

## Installation

### Option 1: Local Installation

1. Clone this repository:

   ```bash
   git clone https://github.com/yourusername/teslamate-mcp.git
   cd teslamate-mcp
   ```

2. Install dependencies using uv (recommended):

   ```bash
   uv sync
   ```

   Or using pip:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root:

   ```env
   DATABASE_URL=postgresql://username:password@hostname:port/teslamate
   ```

### Option 2: Docker Deployment (Remote Access)

For remote deployment using Docker:

```bash
# Clone and navigate to the repository
git clone https://github.com/yourusername/teslamate-mcp.git
cd teslamate-mcp

# Setup environment
cp env.example .env
# Edit .env with your database credentials

# Build and start
docker-compose up -d
```

The remote server will be available at:

- Streamable HTTP: `http://localhost:8888/mcp`

#### Configuring Authentication (Optional)

To secure your remote MCP server with bearer token authentication:

1. Set a bearer token in your `.env` file:

   ```env
   AUTH_TOKEN=your-secret-bearer-token-here
   ```

   Generate a secure token:

   ```bash
   # Use the provided token generator
   python3 utils/generate_token.py
   
   # Or generate manually with openssl
   openssl rand -base64 32
   ```

2. When connecting from MCP clients, include the Authorization header:

   ```json
   {
     "mcpServers": {
       "teslamate-remote": {
         "url": "http://your-server:8888/mcp",
         "transport": "streamable_http",
         "headers": {
           "Authorization": "Bearer your-secret-bearer-token-here"
         }
       }
     }
   }
   ```

## Available Tools

The MCP server provides 20 tools for querying your TeslaMate data:

### Pre-defined Query Tools

1. `get_basic_car_information` - Basic vehicle details (VIN, model, name, color, etc.)
2. `get_current_car_status` - Current state, location, battery level, and temperature
3. `get_software_update_history` - Timeline of software updates
4. `get_battery_health_summary` - Battery degradation and health metrics
5. `get_battery_degradation_over_time` - Historical battery capacity trends
6. `get_daily_battery_usage_patterns` - Daily battery consumption patterns
7. `get_tire_pressure_weekly_trends` - Tire pressure history and trends
8. `get_monthly_driving_summary` - Monthly distance, efficiency, and driving time
9. `get_daily_driving_patterns` - Daily driving habits and patterns
10. `get_longest_drives_by_distance` - Top drives by distance with details
11. `get_total_distance_and_efficiency` - Overall driving statistics
12. `get_drive_summary_per_day` - Daily drive summaries
13. `get_efficiency_by_month_and_temperature` - Efficiency analysis by temperature
14. `get_average_efficiency_by_temperature` - Temperature impact on efficiency
15. `get_unusual_power_consumption` - Anomalous power usage detection
16. `get_charging_by_location` - Charging statistics by location
17. `get_all_charging_sessions_summary` - Complete charging history summary
18. `get_most_visited_locations` - Frequently visited places

### Custom Query Tools

19. `get_database_schema` - Returns complete database schema (tables, columns, data types)
20. `run_sql` - Execute custom SELECT queries with safety validation
    - Only SELECT statements allowed
    - Prevents DROP, CREATE, INSERT, UPDATE, DELETE, ALTER, etc.
    - Blocks multiple statement execution
    - Safely handles strings and comments

## Configuration

### Environment Variables

Create a `.env` file based on `env.example`:

```env
# Database connection (REQUIRED)
DATABASE_URL=postgresql://username:password@hostname:port/teslamate

# Bearer token for authentication (OPTIONAL)
AUTH_TOKEN=

# Custom queries directory (OPTIONAL)
QUERIES_DIR=queries
```

### MCP Client Configuration

#### Cursor IDE

Access through Cursor's settings (⌘+, → search for "MCP"):

**Local Configuration (stdio transport):**

```json
{
  "mcpServers": {
    "teslamate": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/teslamate-mcp",
        "run",
        "main.py"
      ]
    }
  }
}
```

**Note**: If you have a `.env` file, the `DATABASE_URL` will be loaded automatically.

#### Claude Desktop

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

**Local Configuration (stdio transport):**

```json
{
  "mcpServers": {
    "teslamate": {
      "command": "uv",
      "args": ["run", "python", "/path/to/teslamate-mcp/main.py"],
      "env": {
        "DATABASE_URL": "postgresql://username:password@hostname:port/teslamate"
      }
    }
  }
}
```

**Remote Configuration (streamable HTTP transport):**

```json
{
  "mcpServers": {
    "TeslaMate": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://your-private-server:8888/mcp",
        "--allow-http"
      ]
    }
  }
}
```

With authentication:

```json
{
  "mcpServers": {
    "TeslaMate": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://your-private-server:8888/mcp",
        "--allow-http",
        "--header",
        "Authorization:${AUTH_HEADER}"
      ],
      "env": {
        "AUTH_HEADER": "Bearer <secret bearer token>"
      }
    }
  }
}
```

## Usage

### Running the Server

**Local (STDIO):**

```bash
uv run python main.py
```

**Remote (HTTP):**

```bash
# Using Python directly
python main_remote.py --host 0.0.0.0 --port 8888

# Using Docker
docker-compose up -d
```

### Example Queries

Once configured with an MCP client, you can ask natural language questions:

#### Basic Vehicle Information

- "What's my Tesla's basic information?"
- "Show me my current car status"
- "What software updates has my Tesla received?"

#### Battery and Health

- "How is my battery health?"
- "Show me battery degradation over time"
- "What are my daily battery usage patterns?"

#### Driving Analytics

- "Show me my monthly driving summary"
- "What are my daily driving patterns?"
- "What are my longest drives by distance?"

#### Efficiency Analysis

- "How does temperature affect my efficiency?"
- "Show me efficiency trends by month and temperature"

#### Charging and Location Data

- "Where do I charge most frequently?"
- "Show me all my charging sessions summary"
- "What are my most visited locations?"

#### Custom SQL Queries

- "Show me the database schema"
- "Run a SQL query to find drives longer than 100km"
- "Query the average charging power by location"

**Note**: The `run_sql` tool only allows SELECT queries. All data modification operations are strictly forbidden for safety.

## Development

### Project Structure Overview

The project follows a modular architecture:

- **`src/`** - Core modules containing all shared logic
  - **`config.py`** - Configuration management and environment variables
  - **`database.py`** - Database connection pooling and query execution
  - **`tools.py`** - Tool definitions registry (eliminates duplication)
  - **`validators.py`** - SQL query validation and security
  
- **`main.py`** - STDIO transport server for local connections
- **`main_remote.py`** - HTTP transport server for remote connections
- **`queries/`** - SQL query files (one per tool)

### Adding New Queries

1. Create a new SQL file in the `queries/` directory:

   ```sql
   -- queries/my_new_query.sql
   SELECT * FROM my_table;
   ```

2. Add the tool definition in `src/tools.py`:

   ```python
   ToolDefinition(
       name="get_my_new_data",
       description="Description of what this query returns",
       sql_file="my_new_query.sql",
   ),
   ```

3. Restart the server - the new tool will be automatically registered!

### Testing

Run the test script to verify your setup:

```bash
python test_server.py
```

## Security Considerations

- **Use HTTPS in production**: Bearer tokens are sent in plain text. Always use HTTPS/TLS in production.
- **Strong tokens**: Use long, random tokens (at least 32 characters).
- **Environment variables**: Never commit tokens to version control.
- **Network security**: Consider using a VPN or IP restrictions.
- **SQL validation**: Only SELECT queries are allowed; all modification operations are blocked.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [TeslaMate](https://github.com/teslamate-org/teslamate) - Tesla data logging software
- [Model Context Protocol](https://modelcontextprotocol.io/) - Protocol for AI-tool integration

## Contributing

For bugs and feature requests, please open an issue on GitHub.
