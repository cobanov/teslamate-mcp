# TeslaMate MCP Server

A Model Context Protocol (MCP) server that provides access to your TeslaMate database, allowing AI assistants to query Tesla vehicle data and analytics.

## Overview

This MCP server connects to your TeslaMate PostgreSQL database and exposes various tools to retrieve Tesla vehicle information, driving statistics, charging data, battery health, efficiency metrics, and location analytics. It's designed to work with MCP-compatible AI assistants like Claude Desktop, enabling natural language queries about your Tesla data.

## Prerequisites

- [TeslaMate](https://github.com/teslamate-org/teslamate) running with a PostgreSQL database
- Python 3.11 or higher
- Access to your TeslaMate database

## Installation

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

## Configuration

### Environment Variables

- `DATABASE_URL`: PostgreSQL connection string for your TeslaMate database

### MCP Client Configuration

To use this server with Claude Desktop, add the following to your MCP configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

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

## Usage

### Running the Server

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
