# TeslaMate MCP Server

A Model Context Protocol (MCP) server that provides access to your TeslaMate database, allowing AI assistants to query Tesla vehicle data and analytics.

![teslamate-mcp](assets/teslamcp.gif)


## Overview

This MCP server connects to your TeslaMate PostgreSQL database and exposes various tools to retrieve Tesla vehicle information, driving statistics, charging data, battery health, efficiency metrics, and location analytics. It's designed to work with MCP-compatible AI assistants like Claude Desktop, enabling natural language queries about your Tesla data.

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

For remote deployment using Docker. Quick start:

```bash
# Clone and navigate to the repository
git clone https://github.com/yourusername/teslamate-mcp.git
cd teslamate-mcp

# Run the deployment script
./deploy.sh deploy

# Or manually:
cp env.example .env
# Edit .env with your database credentials
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
   python3 generate_token.py
   
   # Or generate manually with openssl
   openssl rand -base64 32
   
   # Or use any other method to create a secure random string
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

3. Or use curl for testing:
   ```bash
   curl -H "Authorization: Bearer your-secret-bearer-token-here" \
        http://localhost:8888/mcp
   ```

#### Security Considerations

- **Use HTTPS in production**: Bearer tokens are sent in plain text. Always use HTTPS/TLS in production environments.
- **Strong tokens**: Use long, random tokens (at least 32 characters).
- **Environment variables**: Never commit tokens to version control. Use environment variables or secrets management.
- **Network security**: Consider using a VPN or restricting access by IP address for additional security.
- **Token rotation**: Regularly rotate your bearer tokens.

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

- `DATABASE_URL`: PostgreSQL connection string for your TeslaMate database

### MCP Client Configuration

To use this server with Claude Desktop, add the following to your MCP configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

#### Local Configuration (stdio transport)

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

#### Remote Configuration (streamable HTTP transport)

For connecting to a remote server:

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

With authentication enabled:

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

### Running the Server (STDIO)

```bash
uv run python main.py
```

### Example Queries

Once configured with an MCP client, you can ask natural language questions organized by category:

#### Basic Vehicle Information

- "What's my Tesla's basic information?"
- "Show me my current car status"
- "What software updates has my Tesla received?"

#### Battery and Health

- "How is my battery health?"
- "Show me battery degradation over time"
- "What are my daily battery usage patterns?"
- "How are my tire pressures trending?"

#### Driving Analytics

- "Show me my monthly driving summary"
- "What are my daily driving patterns?"
- "What are my longest drives by distance?"
- "What's my total distance driven and efficiency?"

#### Efficiency Analysis

- "How does temperature affect my efficiency?"
- "Show me efficiency trends by month and temperature"
- "Are there any unusual power consumption patterns?"

#### Charging and Location Data

- "Where do I charge most frequently?"
- "Show me all my charging sessions summary"
- "What are my most visited locations?"

#### Custom SQL Queries

- "Show me the database schema"
- "Run a SQL query to find drives longer than 100km"
- "Query the average charging power by location"
- "Find all charging sessions at superchargers"

**Note**: The `run_sql` tool only allows SELECT queries. All data modification operations (INSERT, UPDATE, DELETE, DROP, etc.) are strictly forbidden for safety.

## Adding New Queries

1. Create a new SQL file in the `queries/` directory
2. Add a corresponding tool function in `main.py`
3. Follow the existing pattern for error handling and database connections

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [TeslaMate](https://github.com/teslamate-org/teslamate) - Tesla data logging software
- [Model Context Protocol](https://modelcontextprotocol.io/) - Protocol for AI-tool integration

For bugs and feature requests, please open an issue on GitHub.
