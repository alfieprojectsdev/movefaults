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

from field_ops.routers import auth, equipment, logsheets, stations

app = FastAPI(
    title="Field Ops API",
    description="PHIVOLCS CORS station field operations — logsheets, equipment, QR scanning",
    version="0.1.0",
)

# CORS: allow the co-located Vite dev server and the production PWA origin.
# Tighten allowed_origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(stations.router)
app.include_router(logsheets.router)
app.include_router(equipment.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "field-ops-api"}


def start() -> None:
    """CLI entry point: uv run field-ops-api"""
    uvicorn.run("field_ops.main:app", host="0.0.0.0", port=8001, reload=True)
