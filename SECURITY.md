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

### Use a non-superuser role — this matters more than it sounds

We **strongly recommend** connecting `teslamate-mcp` with a dedicated PostgreSQL role that only has `SELECT` privileges on the TeslaMate schema:

```sql
CREATE ROLE teslamate_ro LOGIN PASSWORD '…';
GRANT CONNECT ON DATABASE teslamate TO teslamate_ro;
GRANT USAGE ON SCHEMA public TO teslamate_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO teslamate_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO teslamate_ro;
```

TeslaMate's own Docker Compose sets `POSTGRES_USER=teslamate`, which makes that role a **superuser**. If you point `DATABASE_URL` at it, the guards above still stop every write — but the `READ ONLY` transaction does not restrict superuser-only *read* functions. A model driving `run_sql` could then reach, for example:

```sql
SELECT pg_read_file('/etc/passwd');   -- arbitrary file read in the database container
SELECT pg_ls_dir('/var/lib/postgresql');
SELECT rolname, rolpassword FROM pg_authid;
```

None of these are writes, so none are blocked. The realistic path here is not a network attacker — it is prompt injection steering the model that writes the SQL. A non-superuser role removes the capability entirely, which no application-layer filter can do as reliably.

### Known limitations

- **The row cap can be bypassed.** `run_sql` only wraps a query in `LIMIT` when it finds no `LIMIT` of its own, and that check does not distinguish a nested one — `SELECT * FROM (SELECT … LIMIT 5000000) x` runs uncapped. `statement_timeout` still bounds it in time, but a large result can still consume memory.
- **`/health` is unauthenticated by design** so container health checks can reach it, and it reports a short `detail` string when the database is unreachable. Treat that as information disclosure if you expose the endpoint publicly.
- **Write confirmation is not a security control.** When `ENABLE_CHARGING_WRITES` is on, clients without form elicitation proceed without a confirmation prompt. The column-scoped grant is the boundary.
