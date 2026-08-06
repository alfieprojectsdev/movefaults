"""
Field Ops API — FastAPI application factory.

Entry point: uv run field-ops-api
             (calls start() below, which launches uvicorn)

Architecture note:
  This service shares the PostgreSQL instance with vadase-rt-monitor and the
  central POGF schema. It operates in the 'field_ops' schema namespace.
  The central 'stations' table (public schema) is read via the /stations endpoint.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from field_ops.config import settings
from field_ops.routers import auth, equipment, logsheets, staff, stations

app = FastAPI(
    title="Field Ops API",
    description="PHIVOLCS CORS station field operations — logsheets, equipment, QR scanning",
    version="0.1.0",
)

# CORS: the dev server origins, plus any origin named in FIELD_OPS_CORS_ORIGINS
# (comma-separated). Deploying behind a same-origin rewrite needs no entry here
# at all — that is the preferred shape, since it avoids a preflight round trip
# on a slow link. Wildcards are deliberately not supported: allow_credentials
# with "*" is rejected by browsers anyway, and an open CORS policy on a service
# holding field data is not something to configure by accident.
_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:3000"] + [
    o.strip()
    for o in (settings.field_ops_cors_origins or "").split(",")
    if o.strip() and o.strip() != "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(stations.router)
app.include_router(logsheets.router)
app.include_router(equipment.router)
app.include_router(staff.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "field-ops-api"}


def start() -> None:
    """
    CLI entry point: uv run field-ops-api

    Reads PORT from the environment because container hosts (Fly, Railway,
    Render) assign it at runtime and route to it — a hardcoded 8001 means the
    health check never passes and the deploy is rolled back.

    Reload is opt-in via FIELD_OPS_DEV=1. It was previously always on, which in
    a deployed container wastes memory on a file watcher and can restart the
    process mid-request.
    """
    import os

    dev = os.environ.get("FIELD_OPS_DEV") == "1"
    uvicorn.run(
        "field_ops.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8001")),
        reload=dev,
    )
