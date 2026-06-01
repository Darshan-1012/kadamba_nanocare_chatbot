"""FastAPI application — Nanocare Wellness Report Engine."""
# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware

from app.routes.report import router as report_router

app = FastAPI(
    title="Nanocare Wellness Report Engine",
    description="Synthesizes 5 medical device reports into a unified wellness summary.",
    version="0.1.0",
)

# ── CORS (allow frontend & future app integration) ───────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────
app.include_router(report_router, prefix="/api")


@app.get("/")
async def root():
    return {"service": "Nanocare Wellness Report Engine", "status": "running"}
