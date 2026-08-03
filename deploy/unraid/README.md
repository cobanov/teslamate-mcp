# Unraid

`teslamate-mcp.xml` is a Community Applications template for Unraid. Add it as a
private template, or import it from this repository's raw URL.

The full walkthrough — Cloudflare Tunnel, Access policies, and the MCP Server
Portal — lives in the wiki, contributed by [@batubozkan](https://github.com/batubozkan):

**https://github.com/cobanov/teslamate-mcp/wiki/Unraid-Deployment**

Set `DATABASE_URL` to a read-only PostgreSQL role rather than TeslaMate's own
`teslamate` user; see [SECURITY.md](../../SECURITY.md).
