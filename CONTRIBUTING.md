# Contributing

Thanks for considering a contribution to `teslamate-mcp`. This guide should get you from a fresh clone to a passing PR in a few minutes.

## Setup

```bash
git clone https://github.com/cobanov/teslamate-mcp.git
cd teslamate-mcp
cp env.example .env   # set at least DATABASE_URL
uv sync               # installs runtime + dev dependencies
```

## Day-to-day commands

```bash
uv run teslamate-mcp list-tools         # confirm the package imports
uv run teslamate-mcp stdio              # run the stdio server
uv run teslamate-mcp http               # run the HTTP server
uv run ruff check src tests             # lint
uv run ruff format src tests            # format
uv run pytest                           # full test suite (Docker-backed integration tests skip if Docker is absent)
```

CI runs the same `ruff check`, `ruff format --check`, and `pytest` commands on every push and pull request, so running them locally before pushing means fewer back-and-forth round trips.

## Adding a predefined query

1. Drop a single-statement `SELECT` into [src/teslamate_mcp/queries/](src/teslamate_mcp/queries/) — for example `my_query.sql`.
2. Add a sibling `my_query.toml` with the tool's MCP-facing identity:

   ```toml
   name = "get_my_data"
   description = "One short sentence describing what the tool returns."
   ```

3. Restart the server. The registry picks the file up automatically, and `teslamate-mcp list-tools` should show the new entry.

## Coding conventions

- Python 3.11+, type-annotated.
- Ruff handles both lint and format; please make sure both pass before pushing.
- Prefer composition over inheritance, and avoid speculative abstractions — a bug fix should not pull in unrelated refactors.
- Comments should explain non-obvious *why*, not *what*.

## Commit and PR style

- Keep commits focused: one logical change per commit, with a subject line that fits on one screen.
- Reference issues in the body when applicable.
- Open the PR against `main`. Describe what changed, why, and any user-visible impact.

## Reporting bugs and requesting features

Use the GitHub issue tracker. A useful bug report includes the version (`teslamate-mcp --version`), the command you ran, what you expected, and what actually happened — with logs whenever possible.

For security issues, see [SECURITY.md](SECURITY.md) instead — please do not file public issues for vulnerabilities.
