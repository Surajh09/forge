# Forge control plane (FastAPI + the MCP server mounted at /mcp).
#
# A container rather than a serverless function: the MCP streamable-HTTP
# transport keeps its session manager in the app's lifespan, so the process has
# to stay alive between requests.

FROM python:3.12-slim AS base

# uv resolves from the committed uv.lock, so the image gets exactly the
# dependency set the tests ran against.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first: this layer is cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN uv sync --frozen --no-dev

# Run as a non-root user.
RUN useradd --create-home --uid 10001 forge && chown -R forge:forge /app /opt/venv
USER forge

# Railway (and most hosts) inject PORT and route to it. Binding 0.0.0.0 is
# required — the dev script binds localhost, which would be unreachable here.
ENV PORT=8000
EXPOSE 8000

# `sh -c` so $PORT expands at runtime rather than being passed literally.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
