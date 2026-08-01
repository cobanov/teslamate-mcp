# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

RUN uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/cobanov/teslamate-mcp" \
      org.opencontainers.image.description="MCP server exposing the TeslaMate PostgreSQL database to AI assistants." \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 mcp

WORKDIR /app
COPY --from=builder --chown=mcp:mcp /app/.venv /app/.venv

USER mcp

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8888/health',timeout=3); sys.exit(0 if r.status==200 else 1)" || exit 1

CMD ["teslamate-mcp", "http", "--host", "0.0.0.0", "--port", "8888", "--json-response", "--stateless"]
