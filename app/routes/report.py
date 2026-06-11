"""API routes — report generation, retrieval, and PDF download."""
import hashlib
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse

from app.config import DEVICE_KEYS, REPORTS_DIR
from app.controllers.pipeline import extract_all
from app.engine.synthesizer import synthesize_report
from app.engine.llm_client import check_health
from app.output.html_renderer import render_pdf_async as generate_pdf
from app.engine.patient_history import ensure_table, save_visit, get_history, get_chart_data, get_latest_visit

log = logging.getLogger(__name__)
router = APIRouter()

# ── Ensure MySQL table exists on module load ─────────────────────────
try:
    ensure_table()
except Exception as _e:
    logging.getLogger(__name__).warning(f"MySQL table init deferred: {_e}")

# ── In-memory hash→report_id map for cache lookups ──────────────────
_file_hash_cache: dict[str, str] = {}


def _compute_file_hash(files: dict[str, tuple[bytes, str]]) -> str:
    """Create a deterministic hash from all input file contents.

    Same files (regardless of filename) → same hash → same report.
    """
    h = hashlib.sha256()
    for key in sorted(files.keys()):
        content, _ = files[key]
        h.update(key.encode())
        h.update(content)
    return h.hexdigest()[:16]


def _find_cached_report(file_hash: str) -> dict | None:
    """Check if we already generated a report for this file set."""
    # Check in-memory cache first
    if file_hash in _file_hash_cache:
        report_id = _file_hash_cache[file_hash]
        json_path = REPORTS_DIR / report_id / "report.json"
        if json_path.exists():
            return {"report_id": report_id, "path": json_path}

    # Scan reports directory for hash match
    hash_index = REPORTS_DIR / "hash_index.json"
    if hash_index.exists():
        try:
            index = json.loads(hash_index.read_text(encoding="utf-8"))
            if file_hash in index:
                report_id = index[file_hash]
                json_path = REPORTS_DIR / report_id / "report.json"
                if json_path.exists():
                    _file_hash_cache[file_hash] = report_id
                    return {"report_id": report_id, "path": json_path}
        except Exception:
            pass

    return None


def _save_hash_index(file_hash: str, report_id: str):
    """Save hash→report_id mapping to disk for persistence across restarts."""
    hash_index = REPORTS_DIR / "hash_index.json"
    index = {}
    if hash_index.exists():
        try:
            index = json.loads(hash_index.read_text(encoding="utf-8"))
        except Exception:
            pass
    index[file_hash] = report_id
    hash_index.write_text(json.dumps(index, indent=2), encoding="utf-8")
    _file_hash_cache[file_hash] = report_id


@router.get("/health")
async def health():
    """Check Ollama connectivity and model status."""
    info = await check_health()
    return {"service": "Nanocare Wellness Report Engine", **info}


@router.post("/generate")
async def generate_report(
    ecg: UploadFile = File(..., description="ECG PDF report"),
    hrv: UploadFile = File(..., description="HRV PDF report"),
    nadi: UploadFile = File(..., description="Nadi Tarangini PDF report"),
    biowell: UploadFile = File(..., description="Bio-Well PDF report"),
    biores: UploadFile = File(..., description="Bioresonance PDF report"),
    inbody: UploadFile = File(..., description="InBody image (JPG/PNG)"),
    dmit: UploadFile = File(None, description="DMIT PDF report (optional)"),
    name: str = Form("", description="Patient name"),
    age: str = Form("", description="Patient age"),
    patient_id: str = Form("", description="Patient ID"),
    date: str = Form("", description="Report date"),
):
    """Upload 6 device reports, synthesize unified wellness report.

    If the EXACT same files were uploaded before, returns the cached report
    instantly (no LLM calls). This ensures 100% deterministic results.
    """
    # ── 1. Read uploaded files ───────────────────────────────────────
    files = {}
    for key, upload in [
        ("ecg", ecg), ("hrv", hrv), ("nadi", nadi), ("biowell", biowell),
        ("biores", biores), ("inbody", inbody),
    ]:
        content = await upload.read()
        if not content:
            raise HTTPException(400, f"Empty file for {key}")
        files[key] = (content, upload.filename or f"{key}_upload")

    # DMIT is optional
    if dmit:
        dmit_content = await dmit.read()
        if dmit_content:
            files["dmit"] = (dmit_content, dmit.filename or "dmit_upload")

    # ── 2. Check cache — same files = instant return ─────────────────
    file_hash = _compute_file_hash(files)
    cached = _find_cached_report(file_hash)
    if cached:
        report_id = cached["report_id"]
        log.info(f"[{report_id}] Cache HIT (hash={file_hash}) — returning cached report")
        with open(cached["path"], "r", encoding="utf-8") as f:
            report_data = json.load(f)
        return {
            "report_id": report_id,
            "report": report_data,
            "cached": True,
            "extraction_summary": {},
        }

    log.info(f"Cache MISS (hash={file_hash}) — generating new report")
    report_id = file_hash

    # ── 3. Extract text from all files ───────────────────────────────
    log.info(f"[{report_id}] Extracting text from {len(files)} device files...")
    extractions = await extract_all(files)

    extraction_summary = {}
    for key, result in extractions.items():
        extraction_summary[key] = {
            "pages": result.page_count,
            "text_length": len(result.raw_text),
            "error": result.error,
        }
    log.info(f"[{report_id}] Extraction summary: {extraction_summary}")

    # ── 4. Create report directory ───────────────────────────────────
    report_dir = REPORTS_DIR / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    # ── 5. Save device PDFs for direct parsing ────────────────────────
    biores_pdf_path = None
    biores_content, _ = files.get("biores", (None, None))
    if biores_content:
        biores_pdf_path = str(report_dir / "bioresonance_input.pdf")
        with open(biores_pdf_path, "wb") as bf:
            bf.write(biores_content)

    ecg_pdf_path = None
    ecg_content, _ = files.get("ecg", (None, None))
    if ecg_content:
        ecg_pdf_path = str(report_dir / "ecg_input.pdf")
        with open(ecg_pdf_path, "wb") as ef:
            ef.write(ecg_content)

    hrv_pdf_path = None
    hrv_content, _ = files.get("hrv", (None, None))
    if hrv_content:
        hrv_pdf_path = str(report_dir / "hrv_input.pdf")
        with open(hrv_pdf_path, "wb") as hf:
            hf.write(hrv_content)

    dmit_pdf_path = None
    dmit_content, _ = files.get("dmit", (None, None))
    if dmit_content:
        dmit_pdf_path = str(report_dir / "dmit_input.pdf")
        with open(dmit_pdf_path, "wb") as df:
            df.write(dmit_content)

    biowell_pdf_path = None
    biowell_content, _ = files.get("biowell", (None, None))
    if biowell_content:
        biowell_pdf_path = str(report_dir / "biowell_input.pdf")
        with open(biowell_pdf_path, "wb") as bwf:
            bwf.write(biowell_content)

    log.info(f"[{report_id}] Saved input PDFs for direct parsing")

    # ── 6. Synthesize (deterministic + LLM) ─────────────────────────
    log.info(f"[{report_id}] Synthesizing report...")
    try:
        report_data = await synthesize_report(
            extractions,
            report_dir=str(report_dir),
            biores_pdf_path=biores_pdf_path,
            ecg_pdf_path=ecg_pdf_path,
            hrv_pdf_path=hrv_pdf_path,
            dmit_pdf_path=dmit_pdf_path,
            biowell_pdf_path=biowell_pdf_path,
        )
    except ValueError as e:
        raise HTTPException(500, f"Report synthesis failed: {e}")

    # ── 7. Save report JSON ──────────────────────────────────────────
    # Inject user-supplied patient info (overrides auto-detected values)
    patient = report_data.setdefault("patient", {})
    if name:
        patient["name"] = name
    if age:
        patient["age"] = age
    if patient_id:
        patient["id"] = patient_id
    if date:
        patient["date"] = date

    json_path = report_dir / "report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    # ── 7. Generate PDF ──────────────────────────────────────────────
    pdf_path = report_dir / "summary_wellness_report.pdf"
    try:
        await generate_pdf(report_data, str(pdf_path))
        log.info(f"[{report_id}] PDF generated: {pdf_path}")
    except Exception as e:
        log.error(f"[{report_id}] PDF generation failed: {e}")

    # ── 8. Save hash index for persistence ───────────────────────────
    _save_hash_index(file_hash, report_id)

    # ── 9. Save to patient history (MySQL) ───────────────────────────
    history_data = {}
    if patient_id:
        try:
            save_visit(
                patient_id=patient_id,
                visit_date=date or "",
                report_hash=report_id,
                report_data=report_data,
            )
            history_data = get_chart_data(patient_id)
            log.info(f"[{report_id}] Patient history saved for {patient_id}")
        except Exception as e:
            log.warning(f"[{report_id}] Patient history save failed (non-fatal): {e}")

    log.info(f"[{report_id}] Report generation complete")

    return {
        "report_id": report_id,
        "report": report_data,
        "cached": False,
        "extraction_summary": extraction_summary,
        "history": history_data,
    }


@router.get("/report/{report_id}")
async def get_report(report_id: str):
    """Retrieve a previously generated report by ID."""
    json_path = REPORTS_DIR / report_id / "report.json"
    if not json_path.exists():
        raise HTTPException(404, f"Report {report_id} not found")

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/report/{report_id}/pdf")
async def get_report_pdf(report_id: str):
    """Download the PDF version of a report."""
    pdf_path = REPORTS_DIR / report_id / "summary_wellness_report.pdf"
    # Fallback to old name for backward compatibility
    if not pdf_path.exists():
        pdf_path = REPORTS_DIR / report_id / "wellness_report.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, f"PDF for report {report_id} not found")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"summary_wellness_report_{report_id}.pdf",
    )


# ── Patient History Endpoints ────────────────────────────────────────

@router.get("/patient/{patient_id}/history")
async def patient_history(patient_id: str, limit: int = 10):
    """Get all visit history for a patient."""
    try:
        rows = get_history(patient_id, limit=limit)
        return {"patient_id": patient_id, "visits": rows, "total": len(rows)}
    except Exception as e:
        raise HTTPException(500, f"Failed to retrieve history: {e}")


@router.get("/patient/{patient_id}/history/chart")
async def patient_history_chart(patient_id: str, limit: int = 10):
    """Get chart-ready arrays for frontend charting."""
    try:
        chart = get_chart_data(patient_id, limit=limit)
        return {"patient_id": patient_id, **chart}
    except Exception as e:
        raise HTTPException(500, f"Failed to retrieve chart data: {e}")


@router.get("/patient/{patient_id}/history/latest")
async def patient_history_latest(patient_id: str):
    """Get the most recent visit for a patient."""
    try:
        latest = get_latest_visit(patient_id)
        if not latest:
            raise HTTPException(404, f"No history found for patient {patient_id}")
        return {"patient_id": patient_id, "visit": latest}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to retrieve latest visit: {e}")


# ── Recommendations Endpoint ────────────────────────────────────────

@router.get("/report/{report_id}/recommendations")
async def get_recommendations(report_id: str):
    """Get food/medicine/lifestyle recommendations for a report."""
    json_path = REPORTS_DIR / report_id / "report.json"
    if not json_path.exists():
        raise HTTPException(404, f"Report {report_id} not found")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    recs = data.get("food_recommendations", {})
    if not recs:
        raise HTTPException(404, f"No recommendations found for report {report_id}")
    return {"report_id": report_id, "recommendations": recs}
