FROM python:3.11-slim

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY config/ ./config/

# Install dependencies
RUN uv sync --frozen --no-dev

# Run ingestor
CMD ["uv", "run", "vadase-ingestor"]