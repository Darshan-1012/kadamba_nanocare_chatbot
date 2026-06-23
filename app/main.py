"""FastAPI application — Nanocare Wellness Report Engine."""
import logging
# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware

from app.routes.report import router as report_router
from app.routes.wellness_v1 import router as wellness_v1_router

log = logging.getLogger(__name__)

app = FastAPI(
    title="Nanocare Wellness Report Engine",
    description=(
        "Synthesizes 5 medical device reports into a unified wellness summary.\n\n"
        "**Integration API**: Use `/api/v1/wellness/` endpoints for new integrations.\n\n"
        "**Legacy API**: `/api/generate`, `/api/doctor/*`, `/api/user/*` routes "
        "are deprecated — migrate to v1 endpoints."
    ),
    version="1.0.0",
)

# ── CORS (allow frontend & future app integration) ───────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Key guard (disabled when NANOCARE_API_KEY is unset) ───────────
from app.middleware.api_key import APIKeyMiddleware  # noqa: E402
app.add_middleware(APIKeyMiddleware)


# ── Startup: run idempotent migrations ────────────────────────────────
@app.on_event("startup")
async def startup_migrations():
    """Run database migrations on server startup."""
    try:
        from app.db.migrations import run_migrations
        run_migrations()
        log.info("Startup migrations complete")
    except Exception as e:
        log.error(f"Startup migration failed (server will continue): {e}")


# ── Routes ────────────────────────────────────────────────────────────
app.include_router(report_router, prefix="/api", tags=["legacy"])
app.include_router(wellness_v1_router, prefix="/api/v1/wellness", tags=["wellness-v1"])


@app.get("/")
async def root():
    return {"service": "Nanocare Wellness Report Engine", "version": "1.0.0", "status": "running"}
