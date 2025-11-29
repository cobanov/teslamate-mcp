"""Generate a secure bearer token for TeslaMate MCP Server authentication"""

import secrets

if __name__ == "__main__":
    token = secrets.token_urlsafe(32)
    print(f"AUTH_TOKEN={token}")
