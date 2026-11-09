"""
Varsha — FastAPI application entry point.

Hyperlocal monsoon onset & break prediction (SIH 2026, PS 26086): probabilistic
1-4 week outlooks, risk maps and crop advisories at block / panchayat scale.
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from backend.db.models import Base  # noqa: E402
from backend.db.session import DATABASE_URL, engine  # noqa: E402
from backend.routers import (  # noqa: E402
    advisories, boundaries, dashboard, feedback, forecasts, messaging, officer, pipeline, replay, verification,
)

logger = logging.getLogger("varsha")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Varsha API started (db: %s)", DATABASE_URL.split("@")[-1])
    yield
    await engine.dispose()


app = FastAPI(
    title="Varsha — Monsoon Intelligence System",
    description=(
        "Hybrid teleconnection + machine-learning forecasts of monsoon onset, false onset, dry spells "
        "(breaks) and heavy rain 1-4 weeks ahead at block and panchayat scale, with crop advisories in "
        "Telugu, Hindi and English delivered by SMS / WhatsApp after officer review."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

origins = {"http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000",
           os.getenv("FRONTEND_URL", "http://localhost:3000")}
app.add_middleware(CORSMiddleware, allow_origins=sorted(origins), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(boundaries.router, prefix="/api/v1/boundaries", tags=["Boundaries"])
app.include_router(forecasts.router, prefix="/api/v1/forecasts", tags=["Forecasts"])
app.include_router(advisories.router, prefix="/api/v1/advisories", tags=["Advisories"])
app.include_router(officer.router, prefix="/api/v1/officer", tags=["Officer Console"])
app.include_router(replay.router, prefix="/api/v1/replay", tags=["Replay Mode"])
app.include_router(feedback.router, prefix="/api/v1/feedback", tags=["Farmer Feedback"])
app.include_router(messaging.router, prefix="/api/v1/messaging", tags=["SMS / WhatsApp Gateway"])
app.include_router(verification.router, prefix="/api/v1/verification", tags=["Verification"])
app.include_router(pipeline.router, prefix="/api/v1/pipeline", tags=["Pipeline"])


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "Varsha — Monsoon Intelligence System",
        "version": "1.0.0",
        "status": "running",
        "pilot_region": "Telangana (Mahbubnagar, Nalgonda, Medak)",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
