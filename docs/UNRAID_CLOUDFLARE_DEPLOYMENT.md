# Deploying teslamate-mcp on Unraid behind a Cloudflare MCP Server Portal

This runbook deploys the teslamate-mcp Docker container on an Unraid server and exposes it
to Claude (claude.ai / Claude Desktop / mobile / Claude Code) through **Cloudflare Tunnel** +
a **Cloudflare Zero Trust MCP Server Portal** — no ports opened on the home network.

## Architecture

```
claude.ai / Claude Desktop / mobile / Claude Code
        │  OAuth 2.1 (Cloudflare Access Managed OAuth; policy: allow you@example.com)
        ▼
https://mcp.your-domain.com/mcp                ← MCP Server Portal (Cloudflare edge)
        │  Authorization: Bearer <AUTH_TOKEN>   (portal "Custom Headers" upstream auth)
        ▼
https://teslamate-mcp.your-domain.com/mcp      ← Tunnel public hostname
        │  Cloudflare Tunnel (outbound-only cloudflared on Unraid)
        ▼
[Unraid] cloudflared ──► http://192.168.1.100:8888 (teslamate-mcp container)
                                        └──► TeslaMate PostgreSQL (DATABASE_URL)
```

Why this shape:
- **claude.ai / Claude Desktop custom connectors are OAuth-only** — they cannot send a static
  bearer token. The portal's *Managed OAuth* handles the client-side login (via your
  Cloudflare Access policy), while the portal authenticates *upstream* to teslamate-mcp
  with its built-in `AUTH_TOKEN` as a custom header.
- **Cloudflare Tunnel** makes the container reachable from Cloudflare's edge without any
  inbound firewall/NAT rules.
- Defense in depth: the direct hostname stays bearer-protected; `run_sql` is additionally
  sandboxed server-side (Postgres `READ ONLY` transaction + forced rollback); use a
  SELECT-only DB role for a final layer.

## Values used in this deployment

| Value | Meaning |
|---|---|
| `your-domain.com` | Domain active on Cloudflare |
| `192.168.1.100` | LAN IP of the Unraid server |
| `<AUTH_TOKEN>` | Bearer token generated in Phase 1 (kept out of this file) |
| `you@example.com` | Email allowed by the Access policy |

## Prerequisites

- TeslaMate + PostgreSQL running on Unraid (Docker UI).
- A domain added and active in your Cloudflare account.
- A Cloudflare **Zero Trust** organization (free plan is fine — first-time setup asks you to
  pick a team name at <https://one.dash.cloudflare.com>). The default **One-time PIN**
  identity provider (email code) is sufficient.

---

## Phase 1 — Deploy teslamate-mcp on Unraid

### 1.1 Generate the auth token (on any machine)

```bash
openssl rand -base64 32          # or: uv run teslamate-mcp gen-token
```

Save the value — it is used in the container env **and** in the Cloudflare portal config.

### 1.2 (Recommended) Create a SELECT-only Postgres role

In the TeslaMate PostgreSQL container console (Unraid Docker UI → PostgreSQL container →
Console): `psql -U teslamate teslamate`, then:

```sql
CREATE ROLE teslamate_ro LOGIN PASSWORD '<choose-a-password>';
GRANT CONNECT ON DATABASE teslamate TO teslamate_ro;
GRANT USAGE ON SCHEMA public TO teslamate_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO teslamate_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO teslamate_ro;
```

### 1.3 Add the container

Option A — template: copy `deploy/unraid/teslamate-mcp.xml` to
`/boot/config/plugins/dockerMan/templates-user/` on the Unraid flash share, then
**Docker → Add Container → select template `teslamate-mcp`**.

Option B — manual (**Docker → Add Container**):

| Field | Value |
|---|---|
| Name | `teslamate-mcp` |
| Repository | `ghcr.io/batubozkan/teslamate-mcp:latest` (this repo's release image, v0.4.0+) |
| Network type | `bridge` |
| Port | host `8888` → container `8888` (TCP) |
| Env `DATABASE_URL` | `postgresql://teslamate_ro:<pw>@192.168.1.100:5432/teslamate` (or the main `teslamate` user) |
| Env `AUTH_TOKEN` | `<AUTH_TOKEN>` from step 1.1 |
| Env `REPORT_TIMEZONE` | `Europe/Istanbul` (IANA name; daily/monthly buckets follow local midnight) |
| Env `LOG_LEVEL` | `INFO` |

> **Private image:** `ghcr.io/batubozkan/teslamate-mcp` is a private GHCR package. Before the
> first pull, run `docker login ghcr.io -u batubozkan` on the Unraid terminal with a GitHub
> PAT (classic, `read:packages` scope) — or make the package public in its GitHub settings.
> Releases are published by pushing a `v*` tag (`git tag v0.x.y && git push origin v0.x.y`).

> The image's default command already runs the HTTP transport
> (`teslamate-mcp http --host 0.0.0.0 --port 8888 --json-response`), runs as a non-root
> user, and has a built-in Docker `HEALTHCHECK` on `/health`. Leave **Post Arguments** empty.

> **Historical (only if running the upstream `cobanov/…:0.3.1` image):** that image's
> `--json-response` flag crashes at startup. Workaround: set **Post Arguments** to
> `teslamate-mcp http --host 0.0.0.0 --port 8888`. Fixed in 0.4.0 — the workaround must be
> removed when upgrading, or you'll silently keep SSE-response mode.

> **Postgres reachability:** `192.168.1.100:5432` works when the TeslaMate PostgreSQL
> container publishes port 5432 (the standard Unraid TeslaMate setup does). If it doesn't,
> either publish it or put both containers on the same custom Docker network and use the
> container name as host.

### 1.4 Verify on the LAN

```bash
curl http://192.168.1.100:8888/health
# → {"status":"ok","version":"0.4.0"}

curl -i http://192.168.1.100:8888/mcp
# → HTTP 401 (bearer auth active)
```

> **Important:** `/health` and the 401 check do **not** touch the database. A *missing*
> `DATABASE_URL` fails at startup, but a *wrong* one (bad host/password) only surfaces on
> the **first real MCP request** — the session hangs (SSE pings only), times out, and all
> subsequent requests return `500` until the container is restarted. Never use `localhost`
> as the DB host: inside the container it points at the container itself, not the Unraid
> host. Use `192.168.1.100`. Test connectivity from inside the container with:
> `docker exec teslamate-mcp python -c "import os,psycopg; psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=5); print('DB OK')"`

---

## Phase 2 — Cloudflare Tunnel

### 2.1 Create the tunnel

1. <https://one.dash.cloudflare.com> → **Networks → Tunnels → Create a tunnel** →
   connector type **Cloudflared** → name it `unraid`.
2. Copy the **tunnel token** (long `eyJ…` string) from the install command shown.

### 2.2 Run cloudflared on Unraid

Install **Cloudflared** from Unraid Community Apps (image `cloudflare/cloudflared`), with
post arguments / command:

```
tunnel --no-autoupdate run --token <TUNNEL_TOKEN>
```

The dashboard should show the tunnel status **HEALTHY** within a minute.

### 2.3 Add the public hostname

In the tunnel's **Public hostnames** tab → **Add a public hostname**:

| Field | Value |
|---|---|
| Subdomain | `teslamate-mcp` |
| Domain | `your-domain.com` |
| Type | `HTTP` |
| URL | `192.168.1.100:8888` |

Cloudflare creates the DNS CNAME automatically.

### 2.4 Verify from the internet

```bash
curl https://teslamate-mcp.your-domain.com/health          # → 200 {"status":"ok",...}
curl -i https://teslamate-mcp.your-domain.com/mcp          # → 401 without token
curl -s -X POST https://teslamate-mcp.your-domain.com/mcp \
  -H "Authorization: Bearer <AUTH_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
# → MCP initialize result (serverInfo "teslamate")
```

---

## Phase 3 — Zero Trust MCP server + portal

### 3.1 Register the MCP server

**Zero Trust → Access controls → AI controls → MCP servers tab → Add an MCP server**:

| Field | Value |
|---|---|
| Name | `teslamate-mcp` |
| HTTP URL | `https://teslamate-mcp.your-domain.com/mcp` |
| Authentication | **Custom Headers** → header `Authorization`, value `Bearer <AUTH_TOKEN>` |
| Access policy | Allow → Emails → `you@example.com` |

teslamate-mcp does not implement OAuth/dynamic client registration, so **Custom Headers**
is the correct (and documented) auth method for it. Save — Cloudflare connects, syncs
capabilities, and the server status becomes **Ready** (25 tools as of 0.4.0, 6 prompts, 2 resources).
After deploying a new server version with added/changed tools, force **⋯ → Sync capabilities**
on the MCP server entry (auto-resync is ~2h).

### 3.2 Create the portal

**Zero Trust → Access controls → AI controls → Add MCP server portal**:

| Field | Value |
|---|---|
| Name | `home-mcp` (any) |
| Custom domain | subdomain `mcp`, domain `your-domain.com` (CNAME to `gateway.agents.cloudflare.com` is auto-created) |
| MCP servers | add `teslamate-mcp` |
| Access policy | Allow → Emails → `you@example.com` |

Then edit the portal → **Advanced settings → enable Managed OAuth** (this is what lets MCP
clients like claude.ai authenticate without a browser-cookie flow).

### 3.3 Allowlist client OAuth callbacks (REQUIRED for Claude clients)

Without this, Claude fails at Dynamic Client Registration with *"Couldn't register with …'s
sign-in service"* — Access rejects the client's `redirect_uri`
(`invalid_client_metadata: redirect_uri is not allowed by the account configuration`).

**Zero Trust → Access controls → Applications** → the portal's auto-created application →
**Edit → Advanced settings** → Managed OAuth:

| Setting | Value |
|---|---|
| Allowed redirect URIs | `https://claude.ai/api/mcp/auth_callback` |
| *(second entry)* | `https://claude.com/api/mcp/auth_callback` |
| Allow localhost clients | On (CLI clients like Claude Code) |
| Allow loopback clients | On |

Optional: under the portal's server settings you can disable individual tools (e.g. hide
`run_sql` if you only want the predefined analytics).

The portal endpoint is now: **`https://mcp.your-domain.com/mcp`**

> Capabilities re-sync automatically ~every 2 hours; after adding new queries to the
> server, use **⋯ → Sync capabilities** to refresh immediately.

---

## Phase 4 — Connect clients

### claude.ai / Claude Desktop / mobile (custom connector)

**Settings → Connectors → Add custom connector** → URL `https://mcp.your-domain.com/mcp` →
**Connect** → complete the Cloudflare Access login (email one-time PIN). Tools appear under
the connector; try *"What's my car's current status?"*.

> Note: connectors run from Anthropic's cloud, which is why the portal must be publicly
> reachable (it is — on Cloudflare's edge).

### Claude Code

```bash
claude mcp add --transport http teslamate https://mcp.your-domain.com/mcp
# then inside a session: /mcp → Authenticate (opens browser OAuth)
```

### Cursor / other clients without OAuth support — `mcp-remote` wrapper

```json
{
  "mcpServers": {
    "teslamate": {
      "command": "npx",
      "args": ["-y", "mcp-remote@latest", "https://mcp.your-domain.com/mcp"]
    }
  }
}
```

### OAuth failure modes (claude.ai / Claude Desktop)

Two distinct failures, in the order you're likely to meet them:

1. **"Couldn't register with …'s sign-in service" at Connect** → Dynamic Client Registration
   rejected. Fix: allowlist Claude's callback URIs (Phase 3.3). Diagnose by POSTing a fake
   registration to `https://<team>.cloudflareaccess.com/cdn-cgi/access/oauth/registration` —
   a `redirect_uri is not allowed by the account configuration` body confirms it.
2. **"Authorization with the MCP server failed" before any login screen** (historical,
   reported mid-2026, since fixed on Cloudflare's side in this deployment's testing) —
   caused by a missing `WWW-Authenticate: … resource_metadata=…` header on the portal's 401.
   Verify with `curl -si -X POST https://mcp.<domain>/mcp | grep -i www-authenticate`; the
   header should reference `/.well-known/oauth-protected-resource/mcp`. If it's absent:
   use **Claude Desktop with `mcp-remote`** (config above) as the workaround, or front the
   tunnel origin with a Workers OAuth proxy (`workers-oauth-provider`) as a last resort.

---

## Phase 5 — Verification checklist

- [ ] `curl http://192.168.1.100:8888/health` → 200 (LAN)
- [ ] `curl https://teslamate-mcp.your-domain.com/health` → 200 (tunnel)
- [ ] `curl https://teslamate-mcp.your-domain.com/mcp` without token → **401**
- [ ] MCP initialize with bearer token → success (Phase 2.4)
- [ ] Portal dashboard: server **Ready**, 25 tools synced (0.4.0+)
- [ ] Client connected via portal URL; `get_basic_car_information` returns your car
- [ ] Negative: `run_sql` with `DELETE FROM cars` → rejected (validator + READ ONLY txn)

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Crash at startup: `no field "streamable_http_json_response"` | Only on the old upstream `0.3.1` image — upgrade to `ghcr.io/batubozkan/teslamate-mcp:0.4.0+` (or see the historical workaround in Phase 1.3) |
| Portal shows old tool count after upgrading the container | Sync ran while the container was restarting — re-run **⋯ → Sync capabilities** once `/health` responds |
| GHCR push from release workflow fails `403 Forbidden` | An existing `teslamate-mcp` package isn't linked to the repo (e.g. orphaned from a deleted repo) — delete the stale package or grant the repo **Write** under the package's *Manage Actions access* |
| First MCP call hangs (SSE pings only), then every call `500`s | Container can't reach Postgres (e.g. `localhost` in `DATABASE_URL`) — fix the URL host to `192.168.1.100`, then restart the container |
| `522` on `teslamate-mcp.your-domain.com` | cloudflared container down or wrong service URL in public hostname |
| `522` on `mcp.your-domain.com` | Portal DNS CNAME missing (should point to `gateway.agents.cloudflare.com`) |
| Container restarts at boot | Bad `DATABASE_URL` (fail-fast) — check container log |
| `401` even with token | Token mismatch: compare container `AUTH_TOKEN` vs portal custom header (`Bearer ` prefix included?) |
| Portal server stuck "Sync Required" | Re-save the custom header credentials; **⋯ → Sync capabilities** |
| claude.ai "Authorization failed" at Connect | Known Managed-OAuth/connector issue — see Phase 4 fallbacks |
| Tools list stale after adding a query | Portal syncs ~2h; force with **Sync capabilities** |

## Security notes

- `AUTH_TOKEN` is shared only between the container and the portal config. Anyone hitting
  the direct hostname without it gets 401.
- The MCP server enforces read-only execution for `run_sql` at the Postgres level
  (`READ ONLY` transaction, forced rollback, statement timeout, row cap).
- The `teslamate_ro` SELECT-only role guarantees even the predefined-query path can't write.
- Access policy restricts the portal (and OAuth) to your email; add MFA/IdP in Zero Trust
  if you later share access.
