# Field Ops API container.
#
# BUILD FROM THE REPOSITORY ROOT, not from services/field-ops:
#
#     docker build -f services/field-ops/Dockerfile -t field-ops .
#     fly deploy --dockerfile services/field-ops/Dockerfile
#
# The paths below are relative to the repo root because pyproject.toml and
# uv.lock live there. DEPLOY.md §3 said to `cd services/field-ops` first; that
# is wrong and the build fails on the first COPY.
#
# ── Why there is no frontend stage ─────────────────────────────────────────
#
# There used to be a node stage that ran `npm ci && npm run build` and copied
# the result to ./frontend/dist/. Nothing served it: main.py never mounts
# StaticFiles, and the PWA is served by Vercel. It also made the build
# impossible — that stage's `COPY frontend/package.json` needs the context to
# be services/field-ops, while every COPY below needs the repo root, and no
# single context satisfies both. Removing it fixes the build and drops an
# `npm ci` from every deploy.
#
# ── Why the project is not pip-installed ───────────────────────────────────
#
# pyproject.toml's hatch wheel declares packages/, services/ and tools/ as
# wheel roots, so `uv sync` without --no-install-project tries to build a wheel
# spanning the whole monorepo and fails unless all three trees are copied in —
# which would drag services/field-ops/frontend/node_modules into the image.
# Dependencies are installed on their own and the service runs off PYTHONPATH
# instead. The image stays small and the dependency layer stays cached.

FROM python:3.11-slim AS api

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Dependencies only. This layer is rebuilt only when pyproject.toml or uv.lock
# change, so a source edit redeploys without re-resolving the whole tree.
COPY pyproject.toml uv.lock ./
RUN uv sync --extra field-ops --no-dev --no-install-project

# Service source. field_ops imports nothing outside its own package and the
# third-party deps above, so this is the only tree the runtime needs — src/db/
# is used by the root alembic tree, which runs from an operator's machine, not
# from here.
COPY services/field-ops/src/ ./src/

EXPOSE 8001

# Shell form so ${PORT} is expanded at runtime. Container hosts (Fly, Railway,
# Render) assign the port and route to it; a hardcoded value means the health
# check never passes and the deploy is rolled back. Keep fly.toml's
# internal_port in agreement with the fallback, or set PORT explicitly.
CMD ["sh", "-c", "uv run --no-sync uvicorn field_ops.main:app --host 0.0.0.0 --port ${PORT:-8001}"]
