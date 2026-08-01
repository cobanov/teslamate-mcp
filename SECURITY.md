# Security policy

## Reporting a vulnerability

If you believe you have found a security vulnerability in `teslamate-mcp`, please **do not** open a public GitHub issue. Instead, report it privately so it can be addressed before disclosure.

- Open a [private security advisory](https://github.com/cobanov/teslamate-mcp/security/advisories/new) on GitHub, **or**
- Email the maintainer at <mertcobanov@gmail.com>.

When reporting, please include:

- A description of the vulnerability and its impact.
- Steps to reproduce, ideally with a minimal proof of concept.
- Affected versions or commits.
- Any suggested mitigation or fix.

You can expect an initial acknowledgement within **72 hours** and a status update at least every **7 days** until the issue is resolved.

## Supported versions

Only the most recent minor release receives security fixes. Older versions should upgrade.

## Threat model and hardening notes

`teslamate-mcp` is designed to be reachable only by trusted MCP clients (a local IDE or an authenticated remote deployment). Even so, the server applies defence in depth around the `run_sql` tool:

1. A cheap regex pre-check rejects multi-statement input and non-`SELECT`/`WITH` leading keywords.
2. Queries run inside a PostgreSQL `READ ONLY` transaction with `statement_timeout`, `lock_timeout`, and `idle_in_transaction_session_timeout` enforced via `SET LOCAL`. The transaction is unconditionally rolled back.
3. Result sets are capped: if the user query has no `LIMIT`, the planner sees a wrapped `SELECT * FROM (<q>) LIMIT N`.
4. The HTTP transport supports bearer-token authentication with timing-safe comparison.

We **strongly recommend** connecting `teslamate-mcp` with a dedicated PostgreSQL role that only has `SELECT` privileges on the TeslaMate schema. This way a SQL-layer escape still cannot mutate data.
