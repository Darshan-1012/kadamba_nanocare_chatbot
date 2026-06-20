"""API routes — report generation, retrieval, and PDF download."""
import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse

from app.config import REPORTS_DIR
from app.controllers.pipeline import extract_all
from app.engine.synthesizer import synthesize_report
from app.engine.llm_client import check_health
from app.engine.biorhythm_calculator import build_biorhythm_calendar
from app.output.html_renderer import render_pdf_async as generate_pdf
from app.engine.patient_history import ensure_table, save_visit, get_history, get_chart_data, get_latest_visit
from app.engine.food_knowledge import apply_recommendations_to_wellness

log = logging.getLogger(__name__)
router = APIRouter()
DRAFTS_DIR = REPORTS_DIR / "drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_JSON = "report.json"
REPORT_META_JSON = "metadata.json"
REPORT_PDF = "summary_wellness_report.pdf"

# ── Ensure MySQL table exists on module load ─────────────────────────
try:
    ensure_table()
except Exception as _e:
    logging.getLogger(__name__).warning(f"MySQL table init deferred: {_e}")


def _generated_report_url(request: Request, report_id: str) -> str:
    """Return the public PDF URL for a generated report."""
    return str(request.url_for("get_report_pdf", report_id=report_id))


def _normalize_date_value(value: str) -> str:
    """Normalize accepted date inputs to YYYY-MM-DD, preserving unknown text."""
    text = str(value or "").strip()
    if not text:
        return ""

    formats = [
        "%Y-%m-%d",
        "%d %B %Y",
        "%d %b %Y",
        "%d-%B-%Y",
        "%d-%b-%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%B %Y",
        "%b %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _normalize_patient_dates(report_data: dict) -> dict:
    """Keep patient DOB and report date in one API/report format."""
    patient = report_data.setdefault("patient", {})
    if patient.get("dob"):
        patient["dob"] = _normalize_date_value(patient["dob"])
    if patient.get("date"):
        patient["date"] = _normalize_date_value(patient["date"])
    return report_data


def _repair_unavailable_dimension_descriptions(report_data: dict) -> dict:
    """Use deterministic summary points when a cached AI summary says unavailable."""
    dimensions = report_data.get("dimensions", {})
    for dim in dimensions.values():
        if not isinstance(dim, dict):
            continue
        description = str(dim.get("description") or "").strip()
        if "currently unavailable" not in description.lower() and "data unavailable" not in description.lower():
            continue
        points = [
            str(point).strip()
            for point in dim.get("summary_points", [])
            if str(point).strip()
        ]
        if points:
            dim["description"] = " ".join(points)
    return report_data


def _apply_cached_recommendations(report_data: dict) -> dict:
    """Upgrade cached reports so visible wellness fields use food knowledge."""
    report_data.get("patient", {}).pop("age", None)
    report_data = _normalize_patient_dates(report_data)
    report_data = _repair_unavailable_dimension_descriptions(report_data)
    food_recs = report_data.get("food_recommendations")
    if food_recs:
        report_data["wellness"] = apply_recommendations_to_wellness(
            report_data.get("wellness", {}),
            food_recs,
            nadi_data=None,
        )
    return report_data


# ── In-memory hash→report_id map for cache lookups ──────────────────
_file_hash_cache: dict[str, str] = {}


def _compute_file_hash(
    files: dict[str, tuple[bytes, str]],
    patient_inputs: dict[str, str] | None = None,
) -> str:
    """Create a deterministic hash from all input file contents.

    Same files (regardless of filename) → same hash → same report.
    """
    h = hashlib.sha256()
    for key in sorted(files.keys()):
        content, _ = files[key]
        h.update(key.encode())
        h.update(content)
    for key, value in sorted((patient_inputs or {}).items()):
        value = str(value or "").strip()
        if value:
            h.update(key.encode())
            h.update(value.encode())
    return h.hexdigest()[:16]


def _find_cached_report(file_hash: str) -> dict | None:
    """Check if we already generated a report for this file set."""
    # Check in-memory cache first
    if file_hash in _file_hash_cache:
        report_id = _file_hash_cache[file_hash]
        json_path = REPORTS_DIR / report_id / "report.json"
        if json_path.exists() and _pdf_path(report_id).exists():
            return {"report_id": report_id, "path": json_path}

    # Scan reports directory for hash match
    hash_index = REPORTS_DIR / "hash_index.json"
    if hash_index.exists():
        try:
            index = json.loads(hash_index.read_text(encoding="utf-8"))
            if file_hash in index:
                report_id = index[file_hash]
                json_path = REPORTS_DIR / report_id / "report.json"
                if json_path.exists() and _pdf_path(report_id).exists():
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


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _metadata_path(report_dir: Path) -> Path:
    return report_dir / REPORT_META_JSON


def _load_metadata(report_dir: Path) -> dict:
    path = _metadata_path(report_dir)
    if not path.exists():
        return {}
    try:
        return _read_json(path)
    except Exception:
        return {}


def _write_metadata(report_dir: Path, metadata: dict):
    current = _load_metadata(report_dir)
    current.update(metadata)
    current["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _write_json(_metadata_path(report_dir), current)


def _pdf_path(report_id: str) -> Path:
    pdf_path = REPORTS_DIR / report_id / REPORT_PDF
    if not pdf_path.exists():
        pdf_path = REPORTS_DIR / report_id / "wellness_report.pdf"
    return pdf_path


def _patient_identity(report_data: dict) -> dict:
    patient = report_data.get("patient", {})
    return {
        "id": patient.get("id") or patient.get("patient_id") or "",
        "name": patient.get("name", ""),
        "dob": patient.get("dob", ""),
        "date": patient.get("date", ""),
    }


def _apply_patient_inputs(
    report_data: dict,
    *,
    name: str = "",
    dob: str = "",
    patient_id: str = "",
    date: str = "",
) -> dict:
    """Apply doctor/API patient inputs while preserving DOB/date semantics."""
    patient = report_data.setdefault("patient", {})
    if name:
        patient["name"] = name
    if dob:
        patient["dob"] = dob
    if patient_id:
        patient["id"] = patient_id
    if date:
        patient["date"] = date
    patient.pop("age", None)
    return _normalize_patient_dates(report_data)


def _biowell_raw_from_dir(report_dir: Path) -> str:
    cache_path = report_dir / "cache" / "biowell_raw.txt"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    return ""


def _refresh_biorhythm_calendar(
    report_data: dict,
    report_dir: Path,
    biowell_raw: str = "",
) -> dict:
    """Recompute biorhythm after patient DOB/date edits.

    DOB controls cycle values; patient.date controls the target month when a
    BioWell biorhythm month is not parsed from raw BioWell text.
    """
    report_data = _normalize_patient_dates(report_data)
    patient = report_data.setdefault("patient", {})
    patient.pop("age", None)
    raw_text = biowell_raw or _biowell_raw_from_dir(report_dir)
    calendar_data = build_biorhythm_calendar(patient, raw_text)
    if calendar_data:
        report_data.setdefault("biorhythm", {})["calendar"] = calendar_data
    return report_data


async def _read_report_uploads(
    uploads: dict[str, UploadFile],
    dmit: UploadFile | None = None,
) -> dict[str, tuple[bytes, str]]:
    files: dict[str, tuple[bytes, str]] = {}
    for key, upload in uploads.items():
        content = await upload.read()
        if not content:
            raise HTTPException(400, f"Empty file for {key}")
        files[key] = (content, upload.filename or f"{key}_upload")

    if dmit:
        dmit_content = await dmit.read()
        if dmit_content:
            files["dmit"] = (dmit_content, dmit.filename or "dmit_upload")
    return files


def _stage_device_inputs(
    files: dict[str, tuple[bytes, str]],
    report_dir: Path,
) -> dict[str, str | None]:
    """Persist uploaded files needed by deterministic parsers."""
    paths: dict[str, str | None] = {
        "biores_pdf_path": None,
        "ecg_pdf_path": None,
        "hrv_pdf_path": None,
        "dmit_pdf_path": None,
        "biowell_pdf_path": None,
    }
    mapping = {
        "biores": ("biores_pdf_path", "bioresonance_input.pdf"),
        "ecg": ("ecg_pdf_path", "ecg_input.pdf"),
        "hrv": ("hrv_pdf_path", "hrv_input.pdf"),
        "dmit": ("dmit_pdf_path", "dmit_input.pdf"),
        "biowell": ("biowell_pdf_path", "biowell_input.pdf"),
    }
    for device_key, (path_key, filename) in mapping.items():
        content, _ = files.get(device_key, (None, None))
        if not content:
            continue
        path = report_dir / filename
        with open(path, "wb") as f:
            f.write(content)
        paths[path_key] = str(path)
    return paths


def _extraction_summary(extractions: dict) -> dict:
    return {
        key: {
            "pages": result.page_count,
            "text_length": len(result.raw_text),
            "error": result.error,
        }
        for key, result in extractions.items()
    }


async def _synthesize_from_uploads(
    *,
    report_id: str,
    report_dir: Path,
    files: dict[str, tuple[bytes, str]],
    name: str = "",
    dob: str = "",
    patient_id: str = "",
    date: str = "",
) -> dict:
    """Extract and synthesize report JSON without generating a PDF."""
    report_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"[{report_id}] Extracting text from {len(files)} device files...")
    extractions = await extract_all(files)
    extraction_summary = _extraction_summary(extractions)
    log.info(f"[{report_id}] Extraction summary: {extraction_summary}")

    input_paths = _stage_device_inputs(files, report_dir)
    log.info(f"[{report_id}] Saved input files for direct parsing")

    try:
        report_data = await synthesize_report(
            extractions,
            report_dir=str(report_dir),
            **input_paths,
        )
    except ValueError as e:
        raise HTTPException(500, f"Report synthesis failed: {e}") from e

    report_data = _apply_patient_inputs(
        report_data,
        name=name,
        dob=dob,
        patient_id=patient_id,
        date=date,
    )
    biowell_ext = extractions.get("biowell")
    report_data = _refresh_biorhythm_calendar(
        report_data,
        report_dir,
        biowell_ext.raw_text if biowell_ext else "",
    )
    _write_json(report_dir / REPORT_JSON, report_data)
    return {"report": report_data, "extraction_summary": extraction_summary}


def _approved_report_dirs(patient_id: str | None = None) -> list[tuple[str, Path, dict]]:
    approved: list[tuple[str, Path, dict]] = []
    for report_dir in REPORTS_DIR.iterdir():
        if not report_dir.is_dir() or report_dir.name == DRAFTS_DIR.name:
            continue
        json_path = report_dir / REPORT_JSON
        if not json_path.exists() or not _pdf_path(report_dir.name).exists():
            continue
        metadata = _load_metadata(report_dir)
        if metadata.get("status") not in (None, "", "approved"):
            continue
        try:
            report_data = _apply_cached_recommendations(_read_json(json_path))
        except Exception:
            continue
        patient = _patient_identity(report_data)
        if patient_id and patient.get("id") != patient_id:
            continue
        approved.append((report_dir.name, report_dir, report_data))

    def sort_key(item: tuple[str, Path, dict]):
        _, report_dir, report_data = item
        patient_date = report_data.get("patient", {}).get("date") or ""
        return (patient_date, report_dir.stat().st_mtime)

    return sorted(approved, key=sort_key, reverse=True)


def _load_approved_report(report_id: str) -> dict:
    report_dir = REPORTS_DIR / report_id
    json_path = report_dir / REPORT_JSON
    if not json_path.exists():
        raise HTTPException(404, f"Report {report_id} not found")
    metadata = _load_metadata(report_dir)
    if metadata.get("status") not in (None, "", "approved") or not _pdf_path(report_id).exists():
        raise HTTPException(404, f"Approved report {report_id} not found")
    return _apply_cached_recommendations(_read_json(json_path))


def _find_draft_by_source_hash(
    source_hash: str,
    *,
    status: str = "draft",
) -> tuple[str, Path, dict] | None:
    """Return an existing draft record for the same source hash and status."""
    if not DRAFTS_DIR.exists():
        return None
    for draft_dir in DRAFTS_DIR.iterdir():
        if not draft_dir.is_dir():
            continue
        metadata = _load_metadata(draft_dir)
        if (
            metadata.get("source_hash") == source_hash
            and metadata.get("status", "draft") == status
            and (draft_dir / REPORT_JSON).exists()
        ):
            return draft_dir.name, draft_dir, metadata
    return None


def _next_available_dir_id(root: Path, base_id: str) -> str:
    """Return base_id or a numbered suffix that does not exist under root."""
    if not (root / base_id).exists():
        return base_id
    suffix = 2
    while (root / f"{base_id}_v{suffix}").exists():
        suffix += 1
    return f"{base_id}_v{suffix}"


def _draft_report_id_for_source_hash(source_hash: str) -> str:
    return _next_available_dir_id(DRAFTS_DIR, f"draft_{source_hash}")


def _final_report_id_for_draft(draft_report_id: str, metadata: dict) -> str:
    """Return a final report id distinct from the draft id."""
    source_hash = str(metadata.get("source_hash") or "").strip()
    if source_hash:
        base_id = f"report_{source_hash}"
    elif draft_report_id.startswith("draft_"):
        base_id = f"report_{draft_report_id.removeprefix('draft_')}"
    else:
        base_id = f"report_{draft_report_id}"

    existing = REPORTS_DIR / base_id
    if not existing.exists():
        return base_id
    existing_meta = _load_metadata(existing)
    if existing_meta.get("draft_report_id") == draft_report_id:
        return base_id
    return _next_available_dir_id(REPORTS_DIR, base_id)


def _deep_merge(base: dict, updates: dict) -> dict:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _domain_scores(report_data: dict) -> dict:
    dims = report_data.get("dimensions", {})
    return {
        key: dims.get(key, {}).get("score", 0)
        for key in ("physical", "psychological", "emotional", "spiritual")
    }


def _key_metrics(report_data: dict) -> dict:
    metrics = report_data.get("metrics", {})
    return {
        key: metrics.get(key)
        for key in (
            "weight", "bmi", "bodyFat", "heartRate", "bioEnergy",
            "energyReserve", "lfhfRatio", "nadiPulse",
        )
    }


def _wellness_summary(report_data: dict) -> dict:
    wellness = report_data.get("wellness", {})
    food_recs = report_data.get("food_recommendations", {})
    return {
        "priority_systems": food_recs.get("priority_systems", []),
        "diet": wellness.get("diet", ""),
        "yoga": wellness.get("yoga", ""),
        "physicalActivity": wellness.get("physicalActivity", ""),
        "sleep": wellness.get("sleep", ""),
        "stress": wellness.get("stress", ""),
    }


def _biorhythm_summary(report_data: dict) -> dict:
    calendar = report_data.get("biorhythm", {}).get("calendar", {}) or {}
    today = calendar.get("today", {})
    if not today:
        report_date = report_data.get("patient", {}).get("date", "")
        try:
            parsed_date = datetime.strptime(report_date, "%Y-%m-%d").date()
            if parsed_date.year == calendar.get("year") and parsed_date.month == calendar.get("month"):
                today = next(
                    (day for day in calendar.get("days", []) if day.get("day") == parsed_date.day),
                    {},
                )
        except ValueError:
            today = {}
    graph = calendar.get("graph", {})
    return {
        "month_name": calendar.get("month_name", ""),
        "graph": graph,
        "graph_data": graph,
        "today": today,
        "watch_days": calendar.get("watch_days", []),
    }


def _report_summary_payload(request: Request, report_id: str, report_data: dict) -> dict:
    patient = report_data.get("patient", {})
    return {
        "report_id": report_id,
        "date": patient.get("date", ""),
        "generated_report": str(request.url_for("get_user_report_pdf", report_id=report_id)),
        "summary": _domain_scores(report_data),
        "metrics": _key_metrics(report_data),
        "systems": report_data.get("systems", {}),
        "wellness": _wellness_summary(report_data),
        "biorhythm": _biorhythm_summary(report_data),
    }


def _save_approved_history(report_id: str, report_data: dict) -> dict:
    patient = _patient_identity(report_data)
    patient_id = patient.get("id")
    if not patient_id:
        return {}
    try:
        save_visit(
            patient_id=patient_id,
            visit_date=patient.get("date") or "",
            report_hash=report_id,
            report_data=report_data,
        )
        history_data = get_chart_data(patient_id)
        log.info(f"[{report_id}] Patient history saved for {patient_id}")
        return history_data
    except Exception as e:
        log.warning(f"[{report_id}] Patient history save failed (non-fatal): {e}")
        return {}


@router.get("/health")
async def health():
    """Check Ollama connectivity and model status."""
    info = await check_health()
    return {"service": "Nanocare Wellness Report Engine", **info}


@router.post("/generate")
async def generate_report(
    request: Request,
    ecg: UploadFile = File(..., description="ECG PDF report"),
    hrv: UploadFile = File(..., description="HRV PDF report"),
    nadi: UploadFile = File(..., description="Nadi Tarangini PDF report"),
    biowell: UploadFile = File(..., description="Bio-Well PDF report"),
    biores: UploadFile = File(..., description="Bioresonance PDF report"),
    inbody: UploadFile = File(..., description="InBody image (JPG/PNG)"),
    dmit: UploadFile = File(None, description="DMIT PDF report (optional)"),
    name: str = Form("", description="Patient name"),
    dob: str = Form("", description="Patient date of birth, e.g. 2001-04-17 or 17/04/2001"),
    patient_id: str = Form("", description="Patient ID"),
    date: str = Form("", description="Report date"),
):
    """Upload 6 device reports, synthesize unified wellness report.

    If the EXACT same files were uploaded before, returns the cached report
    instantly (no LLM calls). This ensures 100% deterministic results.
    """
    normalized_dob = _normalize_date_value(dob)
    normalized_date = _normalize_date_value(date)
    files = await _read_report_uploads(
        {
            "ecg": ecg,
            "hrv": hrv,
            "nadi": nadi,
            "biowell": biowell,
            "biores": biores,
            "inbody": inbody,
        },
        dmit=dmit,
    )
    patient_inputs = {
        "name": name,
        "dob": normalized_dob,
        "patient_id": patient_id,
        "date": normalized_date,
    }
    file_hash = _compute_file_hash(files, patient_inputs)
    cached = _find_cached_report(file_hash)
    if cached:
        report_id = cached["report_id"]
        log.info(f"[{report_id}] Cache HIT (hash={file_hash}) — returning cached report")
        with open(cached["path"], "r", encoding="utf-8") as f:
            report_data = json.load(f)
        report_data = _apply_cached_recommendations(report_data)
        return {
            "report_id": report_id,
            "generated_report": _generated_report_url(request, report_id),
            "report": report_data,
            "cached": True,
            "extraction_summary": {},
        }

    log.info(f"Cache MISS (hash={file_hash}) — generating new report")
    report_id = file_hash
    report_dir = REPORTS_DIR / report_id
    result = await _synthesize_from_uploads(
        report_id=report_id,
        report_dir=report_dir,
        files=files,
        name=name,
        dob=normalized_dob,
        patient_id=patient_id,
        date=normalized_date,
    )
    report_data = result["report"]
    extraction_summary = result["extraction_summary"]

    pdf_path = report_dir / REPORT_PDF
    try:
        await generate_pdf(report_data, str(pdf_path))
        log.info(f"[{report_id}] PDF generated: {pdf_path}")
    except Exception as e:
        log.error(f"[{report_id}] PDF generation failed: {e}")
        raise HTTPException(500, f"PDF generation failed: {e}") from e

    _write_metadata(report_dir, {
        "report_id": report_id,
        "status": "approved",
        "source": "legacy_generate",
        "source_hash": file_hash,
        "patient": _patient_identity(report_data),
    })

    _save_hash_index(file_hash, report_id)
    history_data = _save_approved_history(report_id, report_data)

    log.info(f"[{report_id}] Report generation complete")

    return {
        "report_id": report_id,
        "generated_report": _generated_report_url(request, report_id),
        "report": report_data,
        "cached": False,
        "extraction_summary": extraction_summary,
        "history": history_data,
    }


@router.post("/doctor/reports/draft")
async def create_doctor_draft_report(
    ecg: UploadFile = File(..., description="ECG PDF report"),
    hrv: UploadFile = File(..., description="HRV PDF report"),
    nadi: UploadFile = File(..., description="Nadi Tarangini PDF report"),
    biowell: UploadFile = File(..., description="Bio-Well PDF report"),
    biores: UploadFile = File(..., description="Bioresonance PDF report"),
    inbody: UploadFile = File(..., description="InBody image (JPG/PNG)"),
    dmit: UploadFile = File(None, description="DMIT PDF report (optional)"),
    name: str = Form("", description="Patient name"),
    dob: str = Form("", description="Patient date of birth"),
    patient_id: str = Form("", description="Patient ID"),
    date: str = Form("", description="Report date"),
):
    """Create a doctor-review draft report without generating a PDF."""
    normalized_dob = _normalize_date_value(dob)
    normalized_date = _normalize_date_value(date)
    files = await _read_report_uploads(
        {
            "ecg": ecg,
            "hrv": hrv,
            "nadi": nadi,
            "biowell": biowell,
            "biores": biores,
            "inbody": inbody,
        },
        dmit=dmit,
    )
    patient_inputs = {
        "name": name,
        "dob": normalized_dob,
        "patient_id": patient_id,
        "date": normalized_date,
    }
    file_hash = _compute_file_hash(files, patient_inputs)
    existing_draft = _find_draft_by_source_hash(file_hash)
    if existing_draft:
        draft_report_id, draft_dir, metadata = existing_draft
        report_data = _apply_cached_recommendations(_read_json(draft_dir / REPORT_JSON))
        status = metadata.get("status", "draft")
        return {
            "draft_report_id": draft_report_id,
            "report_id": metadata.get("approved_report_id", ""),
            "status": status,
            "report": report_data,
            "cached": True,
            "existing_draft": True,
            "extraction_summary": metadata.get("extraction_summary", {}),
        }

    draft_report_id = _draft_report_id_for_source_hash(file_hash)
    draft_dir = DRAFTS_DIR / draft_report_id

    cached = _find_cached_report(file_hash)
    if cached:
        report_data = _apply_cached_recommendations(_read_json(cached["path"]))
        report_data = _apply_patient_inputs(
            report_data,
            name=name,
            dob=normalized_dob,
            patient_id=patient_id,
            date=normalized_date,
        )
        image_path = report_data.get("biorhythm", {}).get("image_path")
        if image_path and Path(image_path).exists():
            draft_dir.mkdir(parents=True, exist_ok=True)
            draft_image_path = draft_dir / "biorhythm_graph.png"
            shutil.copy2(image_path, draft_image_path)
            report_data.setdefault("biorhythm", {})["image_path"] = str(draft_image_path)
        _write_json(draft_dir / REPORT_JSON, report_data)
        extraction_summary = {}
        cached_from = cached["report_id"]
    else:
        result = await _synthesize_from_uploads(
            report_id=draft_report_id,
            report_dir=draft_dir,
            files=files,
            name=name,
            dob=normalized_dob,
            patient_id=patient_id,
            date=normalized_date,
        )
        report_data = result["report"]
        extraction_summary = result["extraction_summary"]
        cached_from = ""

    _write_metadata(draft_dir, {
        "draft_report_id": draft_report_id,
        "status": "draft",
        "source": "doctor_draft",
        "source_hash": file_hash,
        "cached_from_report_id": cached_from,
        "patient": _patient_identity(report_data),
        "extraction_summary": extraction_summary,
    })

    return {
        "draft_report_id": draft_report_id,
        "status": "draft",
        "report": report_data,
        "cached": bool(cached),
        "extraction_summary": extraction_summary,
    }


@router.get("/doctor/reports/{draft_report_id}")
async def get_doctor_report(draft_report_id: str):
    """Fetch a draft or approved doctor report for review."""
    draft_dir = DRAFTS_DIR / draft_report_id
    json_path = draft_dir / REPORT_JSON
    if not json_path.exists():
        raise HTTPException(404, f"Draft report {draft_report_id} not found")
    metadata = _load_metadata(draft_dir)
    return {
        "draft_report_id": draft_report_id,
        "report_id": metadata.get("approved_report_id", ""),
        "status": metadata.get("status", "draft"),
        "report": _apply_cached_recommendations(_read_json(json_path)),
        "metadata": metadata,
    }


@router.patch("/doctor/reports/{draft_report_id}")
async def update_doctor_draft_report(
    draft_report_id: str,
    payload: dict = Body(...),
):
    """Update doctor edits/overrides in a draft report JSON."""
    draft_dir = DRAFTS_DIR / draft_report_id
    json_path = draft_dir / REPORT_JSON
    if not json_path.exists():
        raise HTTPException(404, f"Draft report {draft_report_id} not found")
    metadata = _load_metadata(draft_dir)
    if metadata.get("status", "draft") != "draft":
        raise HTTPException(409, f"Report {draft_report_id} is not editable")

    report_data = _read_json(json_path)
    updates = payload.get("report", payload)
    if not isinstance(updates, dict):
        raise HTTPException(400, "PATCH payload must be a JSON object")
    report_data = _deep_merge(report_data, updates)
    report_data = _refresh_biorhythm_calendar(report_data, draft_dir)
    _write_json(json_path, report_data)
    _write_metadata(draft_dir, {"patient": _patient_identity(report_data)})

    return {
        "draft_report_id": draft_report_id,
        "status": "draft",
        "report": report_data,
    }


@router.post("/doctor/reports/{draft_report_id}/approve")
async def approve_doctor_draft_report(request: Request, draft_report_id: str):
    """Approve a draft, generate final PDF, and save approved patient history."""
    draft_dir = DRAFTS_DIR / draft_report_id
    draft_json = draft_dir / REPORT_JSON
    if not draft_json.exists():
        raise HTTPException(404, f"Draft report {draft_report_id} not found")
    metadata = _load_metadata(draft_dir)
    if metadata.get("status", "draft") != "draft":
        approved_id = metadata.get("approved_report_id")
        if approved_id:
            report_data = _load_approved_report(approved_id)
            return {
                "report_id": approved_id,
                "draft_report_id": draft_report_id,
                "status": "approved",
                "generated_report": _generated_report_url(request, approved_id),
                "summary": _report_summary_payload(request, approved_id, report_data),
            }
        raise HTTPException(409, f"Report {draft_report_id} cannot be approved")

    report_id = _final_report_id_for_draft(draft_report_id, metadata)
    final_dir = REPORTS_DIR / report_id
    if final_dir.exists():
        final_metadata = _load_metadata(final_dir)
        if final_metadata.get("status") == "approved" and _pdf_path(report_id).exists():
            report_data = _load_approved_report(report_id)
            _write_metadata(draft_dir, {
                "status": "approved",
                "approved_report_id": report_id,
                "patient": _patient_identity(report_data),
            })
            return {
                "report_id": report_id,
                "draft_report_id": draft_report_id,
                "status": "approved",
                "generated_report": _generated_report_url(request, report_id),
                "summary": _report_summary_payload(request, report_id, report_data),
                "history": _save_approved_history(report_id, report_data),
            }
    else:
        shutil.copytree(draft_dir, final_dir)

    report_data = _read_json(draft_json)
    _write_json(final_dir / REPORT_JSON, report_data)
    biorhythm = report_data.get("biorhythm", {})
    final_graph = final_dir / "biorhythm_graph.png"
    if final_graph.exists() and biorhythm.get("image_path"):
        biorhythm["image_path"] = str(final_graph)
    report_data = _refresh_biorhythm_calendar(report_data, final_dir)
    _write_json(final_dir / REPORT_JSON, report_data)

    pdf_path = final_dir / REPORT_PDF
    try:
        await generate_pdf(report_data, str(pdf_path))
        log.info(f"[{report_id}] Approved PDF generated: {pdf_path}")
    except Exception as e:
        log.error(f"[{report_id}] Approved PDF generation failed: {e}")
        raise HTTPException(500, f"PDF generation failed: {e}") from e

    _write_metadata(final_dir, {
        "report_id": report_id,
        "draft_report_id": draft_report_id,
        "status": "approved",
        "source": "doctor_approval",
        "source_hash": metadata.get("source_hash", ""),
        "patient": _patient_identity(report_data),
    })
    _write_metadata(draft_dir, {
        "status": "approved",
        "approved_report_id": report_id,
        "patient": _patient_identity(report_data),
    })

    history_data = _save_approved_history(report_id, report_data)
    return {
        "report_id": report_id,
        "draft_report_id": draft_report_id,
        "status": "approved",
        "generated_report": _generated_report_url(request, report_id),
        "summary": _report_summary_payload(request, report_id, report_data),
        "history": history_data,
    }


@router.get("/report/{report_id}")
async def get_report(report_id: str):
    """Retrieve a previously generated report by ID."""
    json_path = REPORTS_DIR / report_id / "report.json"
    if not json_path.exists():
        raise HTTPException(404, f"Report {report_id} not found")

    with open(json_path, "r", encoding="utf-8") as f:
        return _apply_cached_recommendations(json.load(f))


@router.get("/report/{report_id}/pdf")
async def get_report_pdf(report_id: str):
    """Download the PDF version of a report."""
    pdf_path = _pdf_path(report_id)
    if not pdf_path.exists():
        raise HTTPException(404, f"PDF for report {report_id} not found")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"summary_wellness_report_{report_id}.pdf",
    )


# ── User Dashboard Endpoints (approved reports only) ─────────────────

@router.get("/user/patient/{patient_id}/dashboard")
async def get_user_patient_dashboard(
    request: Request,
    patient_id: str,
    detail: str = "compact",
    limit: int = 10,
):
    """Return dashboard data for the latest approved report and history."""
    approved_reports = _approved_report_dirs(patient_id=patient_id)
    latest = approved_reports[0] if approved_reports else None

    patient = {"id": patient_id, "name": "", "dob": ""}
    latest_payload = None
    if latest:
        latest_id, _, latest_data = latest
        latest_patient = latest_data.get("patient", {})
        patient = {
            "id": patient_id,
            "name": latest_patient.get("name", ""),
            "dob": latest_patient.get("dob", ""),
        }
        latest_payload = _report_summary_payload(request, latest_id, latest_data)
        if detail == "full":
            latest_payload["report"] = latest_data

    try:
        history = get_chart_data(patient_id, limit=limit)
    except Exception as e:
        log.warning(f"User dashboard history unavailable for {patient_id}: {e}")
        history = {"dates": [], "stats": {}, "dimensions": {}, "systems": {}, "visit_count": 0}

    reports = [
        _report_summary_payload(request, report_id, report_data)
        for report_id, _, report_data in approved_reports[:limit]
    ]
    return {
        "patient": patient,
        "latest_report": latest_payload,
        "history": history,
        "reports": reports,
    }


@router.get("/user/patient/{patient_id}/reports")
async def get_user_patient_reports(
    request: Request,
    patient_id: str,
    detail: str = "compact",
    limit: int = 20,
):
    """Return approved reports for a patient; drafts are never included."""
    approved_reports = _approved_report_dirs(patient_id=patient_id)[:limit]
    reports = []
    for report_id, _, report_data in approved_reports:
        payload = _report_summary_payload(request, report_id, report_data)
        if detail == "full":
            payload["report"] = report_data
        reports.append(payload)
    return {"patient_id": patient_id, "reports": reports, "total": len(reports)}


@router.get("/user/report/{report_id}/summary")
async def get_user_report_summary(request: Request, report_id: str):
    """Return an approved report summary for web/mobile dashboards."""
    report_data = _load_approved_report(report_id)
    return _report_summary_payload(request, report_id, report_data)


@router.get("/user/report/{report_id}/pdf")
async def get_user_report_pdf(report_id: str):
    """Download an approved report PDF only."""
    _load_approved_report(report_id)
    pdf_path = _pdf_path(report_id)
    if not pdf_path.exists():
        raise HTTPException(404, f"PDF for report {report_id} not found")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"summary_wellness_report_{report_id}.pdf",
    )


@router.get("/user/report/{report_id}")
async def get_user_report(report_id: str, detail: str = "full"):
    """Return approved full report JSON, or compact summary fields if requested."""
    report_data = _load_approved_report(report_id)
    if detail == "compact":
        return {
            "report_id": report_id,
            "date": report_data.get("patient", {}).get("date", ""),
            "summary": _domain_scores(report_data),
            "metrics": _key_metrics(report_data),
            "systems": report_data.get("systems", {}),
            "wellness": _wellness_summary(report_data),
            "biorhythm": _biorhythm_summary(report_data),
        }
    return {"report_id": report_id, "report": report_data}


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
