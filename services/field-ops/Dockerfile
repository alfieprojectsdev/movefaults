# ── Stage 1: Build React PWA ─────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# Output: /app/frontend/dist/

# ── Stage 2: Python API ───────────────────────────────────────────────────────
FROM python:3.11-slim AS api

WORKDIR /app

# Install uv for fast dependency installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy monorepo root files needed for the build
COPY pyproject.toml uv.lock ./
RUN uv sync --extra field-ops --no-dev

# Copy service source
COPY services/field-ops/src/ ./src/
COPY src/db/ ./src/db/

# Copy built frontend into a location the API can serve
COPY --from=frontend-build /app/frontend/dist/ ./frontend/dist/

# Add static file serving to the FastAPI app in production
# (mount /frontend/dist as StaticFiles — see main.py TODO comment)

EXPOSE 8001

CMD ["uv", "run", "field-ops-api"]
