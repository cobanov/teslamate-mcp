<p align="center">
  <img src="assets/teslamcp.gif" alt="teslamate-mcp" width="640">
</p>

<p align="center">
  Ask your Tesla questions in plain language. Your own TeslaMate database,
  answered by whichever AI client you already use.
</p>

<p align="center">
  <a href="https://github.com/cobanov/teslamate-mcp/releases/latest"><img alt="release" src="https://img.shields.io/github/v/release/cobanov/teslamate-mcp?color=e82127&labelColor=1a1a1a"></a>
  <a href="https://github.com/cobanov/teslamate-mcp/pkgs/container/teslamate-mcp"><img alt="ghcr" src="https://img.shields.io/badge/ghcr.io-multi--arch-e82127?labelColor=1a1a1a"></a>
  <img alt="tools" src="https://img.shields.io/badge/tools-35-e82127?labelColor=1a1a1a">
  <a href="https://github.com/cobanov/teslamate-mcp/actions/workflows/ci.yml"><img alt="ci" src="https://img.shields.io/github/actions/workflow/status/cobanov/teslamate-mcp/ci.yml?branch=main&label=ci&color=e82127&labelColor=1a1a1a"></a>
  <a href="LICENSE"><img alt="licence" src="https://img.shields.io/badge/licence-MIT-e82127?labelColor=1a1a1a"></a>
</p>

<p align="center">
  <b><a href="https://github.com/cobanov/teslamate-mcp/wiki">Documentation</a></b> ·
  <a href="https://github.com/cobanov/teslamate-mcp/wiki/Tool-Reference">Tool reference</a> ·
  <a href="https://github.com/cobanov/teslamate-mcp/wiki/Configuration">Configuration</a> ·
  <a href="https://github.com/cobanov/teslamate-mcp/wiki/Deployment">Deployment</a>
</p>

---

[TeslaMate](https://github.com/teslamate-org/teslamate) records everything your car does into PostgreSQL, and its Grafana dashboards answer the questions someone anticipated. The interesting ones usually arrive later — *is the battery actually degrading or was it just cold?*, *what did charging cost me at home versus on the road?*, *which drive was that weirdly inefficient one?*

This is a [Model Context Protocol](https://modelcontextprotocol.io/) server that hands that database to an AI client, so those questions get answered without you writing SQL.

```
You  ▸ has my battery actually degraded this year?

     ⚙ get_battery_capacity_trend(days=365)

     Usable capacity, estimated from your charging sessions rather
     than rated range:

       2025-11    53.8 kWh
       2026-02    53.1 kWh
       2026-07    52.4 kWh

     About 2.6% over eight months, which is unremarkable. The
     February dip tracks outside temperature, not capacity —
     get_average_efficiency_by_temperature shows the same shape.
```

- **35 tools.** 30 analytics and search queries, `run_sql` for anything they don't cover, live schema introspection, and 3 interactive chart tools.
- **Filterable, not fixed.** Every report takes optional `car_name`, `days`, `limit`, and threshold arguments. Call one with no arguments and you get the full classic report.
- **Charts in the conversation.** On MCP Apps-capable clients, `show_charging_curve`, `show_battery_degradation`, and `show_drive_route` render self-contained SVG. Everywhere else they return the same rows.
- **Read-only unless you say otherwise.** `run_sql` executes in a `READ ONLY` transaction that is always rolled back. The single write tool is off by default and can only touch one column.
- **Local or remote.** stdio for Claude Desktop and Cursor, streamable HTTP with bearer auth for everything else.

## Install

Requires a running TeslaMate with PostgreSQL, and Python 3.11+ (or just Docker).

```bash
git clone https://github.com/cobanov/teslamate-mcp.git
cd teslamate-mcp
cp env.example .env      # set DATABASE_URL
uv sync
```

Point your client at it — for Claude Desktop or Cursor:

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

Ask it something. `teslamate-mcp list-tools` prints everything it found.

## Remote

```bash
docker run -d -p 8888:8888 \
  -e DATABASE_URL='postgresql://teslamate:…@host:5433/teslamate' \
  -e AUTH_TOKEN="$(uv run teslamate-mcp gen-token | cut -d= -f2)" \
  ghcr.io/cobanov/teslamate-mcp:latest
```

The endpoint is `/mcp`, the probe is `/health`. Multi-arch images (`amd64`, `arm64`) ship with every release.

> This database is your location history. Keep it on a private network — a VPN or Tailscale — rather than the open internet. [Deployment](https://github.com/cobanov/teslamate-mcp/wiki/Deployment) covers the options.

## Documentation

Everything beyond this page lives in **[the wiki](https://github.com/cobanov/teslamate-mcp/wiki)**:

| | |
|---|---|
| [Tool Reference](https://github.com/cobanov/teslamate-mcp/wiki/Tool-Reference) | All 35 tools, their parameters, what each returns |
| [Configuration](https://github.com/cobanov/teslamate-mcp/wiki/Configuration) | Every environment variable, with guidance |
| [Deployment](https://github.com/cobanov/teslamate-mcp/wiki/Deployment) | Docker, images, proxies, exposure, troubleshooting |
| [Writing Queries](https://github.com/cobanov/teslamate-mcp/wiki/Writing-Queries) | Add your own tool with a `.sql` + `.toml` pair — no Python |
| [Write Tools](https://github.com/cobanov/teslamate-mcp/wiki/Write-Tools) | The opt-in charging-cost write path and its grant |
| [Development](https://github.com/cobanov/teslamate-mcp/wiki/Development) | Setup, tests, layout, releasing |

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Adding a query needs no Python at all: drop a `.sql` file and a `.toml` sidecar into `src/teslamate_mcp/queries/` and the registry picks it up.

A large part of the 0.9 feature line — typed parameters, twelve new queries, MCP Apps, and the SDK v2 migration — was contributed by [@batubozkan](https://github.com/batubozkan).

## License

MIT — see [LICENSE](LICENSE).

<p align="center">
  <a href="https://mseep.ai/app/cobanov-teslamate-mcp"><img src="https://mseep.net/pr/cobanov-teslamate-mcp-badge.png" alt="MseeP.ai security audit" width="200"></a>
  &nbsp;
  <a href="https://glama.ai/mcp/servers/@cobanov/teslamate-mcp"><img src="https://glama.ai/mcp/servers/@cobanov/teslamate-mcp/badge" alt="Glama MCP catalog" width="200"></a>
  &nbsp;
  <a href="https://archestra.ai/mcp-catalog/cobanov__teslamate-mcp"><img src="https://archestra.ai/mcp-catalog/api/badge/quality/cobanov/teslamate-mcp" alt="Archestra Trust Score"></a>
</p>
