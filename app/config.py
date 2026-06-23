"""App-level settings loaded from .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── API Security ──────────────────────────────────────────────────────
# When set, all API requests must include: X-API-Key: <this value>
# Leave empty/unset for local development (middleware is bypassed).
API_KEY: str = os.getenv("NANOCARE_API_KEY", "")

# ── Ollama ────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
# Stronger model for AI-generated clinical summaries (falls back to OLLAMA_MODEL)
OLLAMA_SUMMARY_MODEL: str = os.getenv("OLLAMA_SUMMARY_MODEL", OLLAMA_MODEL)

# ── Paths ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", str(BASE_DIR / "reports")))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Limits ────────────────────────────────────────────────────────────
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))

# ── Device file keys (order matters for display) ─────────────────────
DEVICE_KEYS = ["ecg", "hrv", "nadi", "biowell", "biores", "inbody", "dmit"]
PDF_DEVICES = ["ecg", "hrv", "nadi", "biowell", "biores", "dmit"]
IMAGE_DEVICES = ["inbody"]
