# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
