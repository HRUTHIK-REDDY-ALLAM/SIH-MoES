"""
Varsha — FastAPI Application Entry Point

Monsoon Intelligence System for Indian Agriculture.
Provides probabilistic forecasts, crop advisories, and risk maps
for block and panchayat level planning in Telangana.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from backend.routers import forecasts, advisories, officer, replay, feedback, boundaries


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: verify DB connection, load config
    print("[Varsha] Monsoon Intelligence System starting up...")
    yield
    # Shutdown: cleanup
    print("[Varsha] Monsoon Intelligence System shutting down...")


app = FastAPI(
    title="Varsha — Monsoon Intelligence System",
    description=(
        "Hybrid probabilistic forecasting for monsoon onset, dry spells, "
        "and heavy rain at block/panchayat level. Generates crop-specific "
        "advisories for Indian farmers in regional languages."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        os.getenv("FRONTEND_URL", "http://localhost:3000"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(boundaries.router, prefix="/api/v1/boundaries", tags=["Boundaries"])
app.include_router(forecasts.router, prefix="/api/v1/forecasts", tags=["Forecasts"])
app.include_router(advisories.router, prefix="/api/v1/advisories", tags=["Advisories"])
app.include_router(officer.router, prefix="/api/v1/officer", tags=["Officer Console"])
app.include_router(replay.router, prefix="/api/v1/replay", tags=["Replay Mode"])
app.include_router(feedback.router, prefix="/api/v1/feedback", tags=["Farmer Feedback"])


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "Varsha — Monsoon Intelligence System",
        "version": "0.1.0",
        "status": "running",
        "pilot_region": "Telangana (Mahbubnagar, Nalgonda, Medak)",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
