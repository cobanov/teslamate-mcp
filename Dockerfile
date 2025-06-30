# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./
COPY uv.lock ./

# Install project dependencies using pip
# Convert pyproject.toml dependencies to pip format
RUN pip install --no-cache-dir \
    "black>=25.1.0" \
    "isort>=6.0.1" \
    "mcp[cli]>=1.10.1" \
    "psycopg[binary]>=3.2.9" \
    "psycopg-pool>=3.2.0" \
    "python-dotenv>=1.0.0" \
    "click>=8.1.0" \
    "uvicorn>=0.25.0" \
    "starlette>=0.36.0"

# Copy the application code
COPY main_remote.py ./
COPY queries/ ./queries/
COPY all_db_info.json ./

# Create a non-root user
RUN useradd -m -u 1000 mcp && chown -R mcp:mcp /app
USER mcp

# Expose the HTTP port
EXPOSE 8888

# Run the MCP server
# Default port 8888, host 0.0.0.0, can be overridden with environment variables
CMD ["python", "main_remote.py", "--host", "0.0.0.0", "--port", "8888", "--json-response"] 