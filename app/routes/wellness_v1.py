"""Wellness Integration API v1 — production-ready versioned routes.

Designed as an integration API: the external system provides doctor_id and
patient_id; this API manages wellness report drafts, approval, PDF generation,
and approved-report access for user/customer dashboards.

Mount at: ``/api/v1/wellness``
"""
import json
import logging
import shutil
from copy import deepcopy
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import REPORTS_DIR
from app.engine.dmit_parser import safe_personality_label
from app.engine.llm_client import check_health
from app.output.html_renderer import render_pdf_async as generate_pdf
from app.engine.patient_history import get_chart_data
from app.services import draft_service
from app.routes._helpers import (
    DRAFTS_DIR,
    REPORT_JSON,
    REPORT_PDF,
    normalize_date_value,
    apply_patient_inputs,
    patient_identity,
    read_json,
    write_json,
    write_metadata,
    load_metadata,
    compute_file_hash,
    find_cached_report,
    save_hash_index,
    pdf_path,
    apply_cached_recommendations,
    deep_merge,
    refresh_biorhythm_calendar,
    read_report_uploads,
    synthesize_from_uploads,
    domain_scores,
    key_metrics,
    wellness_summary,
    biorhythm_summary,
    save_approved_history,
    next_available_dir_id,
)

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", summary="Health check")
async def v1_health():
    """Check service and LLM connectivity from the v1 API base URL."""
    info = await check_health()
    return {"service": "Nanocare Wellness Report Engine", "api_version": "v1", **info}


def _v1_report_links(report_id: str, patient_id: str = "", audience: str = "doctor") -> dict:
    """Build relative v1 resource links that clients can call with auth headers."""
    doctor_links = {
        "doctor_report": f"/api/v1/wellness/doctor/reports/{report_id}",
        "doctor_report_summary": f"/api/v1/wellness/doctor/reports/{report_id}/summary",
        "doctor_pdf_download": f"/api/v1/wellness/doctor/reports/{report_id}/pdf",
    }
    patient_links = {}
    if patient_id:
        patient_base = f"/api/v1/wellness/patients/{patient_id}/reports/{report_id}"
        patient_links = {
            "patient_report": patient_base,
            "patient_report_summary": f"{patient_base}/summary",
            "patient_pdf_download": f"{patient_base}/pdf",
        }
    if audience == "patient":
        return patient_links
    if audience == "all":
        return {**doctor_links, **patient_links}
    return doctor_links


def _v1_download_requires() -> str:
    return "X-API-Key header"


def _v1_body_systems(report_data: dict) -> dict:
    """Merge system scores with generated functional summaries."""
    report_data = report_data or {}
    systems = report_data.get("systems", {}) or {}
    summaries = report_data.get("system_summaries", {}) or {}
    return {
        key: {
            **(item if isinstance(item, dict) else {"value": item}),
            "functional_summary": summaries.get(key, ""),
        }
        for key, item in systems.items()
    }


def _v1_dmit_summary(report_data: dict) -> dict:
    """Return the DMIT block in a display-friendly but complete shape."""
    report_data = report_data or {}
    dmit = report_data.get("dmit", {}) or {}
    if not dmit:
        return {"available": False}
    personality = dmit.get("personality", {}) or {}
    return {
        "available": True,
        "patient": dmit.get("patient", {}),
        "brain_dominance": dmit.get("brain_dominance", {}),
        "tfrc": dmit.get("tfrc", {}),
        "multiple_intelligences": dmit.get("multiple_intelligences", {}),
        "brain_lobes": dmit.get("brain_lobes", {}),
        "learning_styles": dmit.get("learning_styles", {}),
        "personality": {
            "primary": safe_personality_label(personality.get("primary")),
            "secondary": safe_personality_label(personality.get("secondary")),
        },
        "planning": dmit.get("planning", {}),
        "swot": dmit.get("swot", {}),
        "brain_traits": dmit.get("brain_traits", {}),
        "neuron_distribution": dmit.get("neuron_distribution", {}),
    }


def _v1_wellness_offerings(report_data: dict) -> dict:
    """Group wellness guidance so doctor/customer UIs are easier to scan."""
    report_data = report_data or {}
    wellness = report_data.get("wellness", {}) or {}
    food = report_data.get("food_recommendations", {}) or {}
    diet = food.get("diet", {}) or {}
    lifestyle = food.get("lifestyle", {}) or {}
    return {
        "nutrition": {
            "summary": wellness.get("diet", ""),
            "recommended": diet.get("recommended", []),
            "avoid": diet.get("avoid", []),
            "functional_foods": food.get("functional_foods", []),
        },
        "movement": {
            "yoga": food.get("yoga", []) or wellness.get("yoga", ""),
            "physical_activity": wellness.get("physicalActivity", ""),
        },
        "recovery": {
            "sleep": wellness.get("sleep", ""),
            "stress": wellness.get("stress", ""),
        },
        "support": {
            "supplements": wellness.get("supplements", ""),
            "medicine": wellness.get("medicine", ""),
            "medicines": food.get("medicines", []),
            "herbal_support": food.get("herbal_support", []),
        },
        "lifestyle": {
            "dos": lifestyle.get("dos", []),
            "donts": lifestyle.get("donts", []),
        },
        "priority_systems": food.get("priority_systems", []),
    }


def _v1_biorhythm_calendar(report_data: dict) -> dict:
    """Return full day-by-day biorhythm calendar for customer views."""
    report_data = report_data or {}
    calendar = report_data.get("biorhythm", {}).get("calendar", {}) or {}
    return {
        "month_name": calendar.get("month_name", ""),
        "year": calendar.get("year"),
        "month": calendar.get("month"),
        "first_weekday": calendar.get("first_weekday", 0),
        "num_days": calendar.get("num_days", 0),
        "today": biorhythm_summary(report_data).get("today", {}),
        "days": calendar.get("days", []),
        "watch_days": calendar.get("watch_days", []),
        "graph": calendar.get("graph", {}),
        "rules": calendar.get("rules", {}),
    }


def _v1_public_report(report_data: dict) -> dict:
    """Add v1 display sections while preserving the original report keys."""
    report_data = report_data or {}
    public_report = deepcopy(report_data)
    dmit = public_report.get("dmit")
    if isinstance(dmit, dict):
        personality = dmit.get("personality", {}) or {}
        dmit["personality"] = {
            "primary": safe_personality_label(personality.get("primary")),
            "secondary": safe_personality_label(personality.get("secondary")),
        }
    public_report["body_systems"] = _v1_body_systems(report_data)
    public_report["functional_summary"] = report_data.get("system_summaries", {}) or {}
    public_report["dmit_summary"] = _v1_dmit_summary(report_data)
    public_report["wellness_offerings"] = _v1_wellness_offerings(report_data)
    public_report["biorhythm_calendar"] = _v1_biorhythm_calendar(report_data)
    return public_report


def _v1_summary_payload(report_id: str, report_data: dict, audience: str = "doctor") -> dict:
    """Build a compact summary payload for user/customer dashboards."""
    patient = report_data.get("patient", {})
    patient_id = patient.get("id") or patient.get("patient_id") or ""
    return {
        "report_id": report_id,
        "patient_id": patient_id,
        "date": patient.get("date", ""),
        "links": _v1_report_links(report_id, patient_id, audience),
        "download_requires": _v1_download_requires(),
        "summary": domain_scores(report_data),
        "dimensions": report_data.get("dimensions", {}),
        "metrics": key_metrics(report_data),
        "systems": report_data.get("systems", {}),
        "body_systems": _v1_body_systems(report_data),
        "functional_summary": report_data.get("system_summaries", {}) or {},
        "interpretations": report_data.get("interpretations", {}) or {},
        "wellness": wellness_summary(report_data),
        "wellness_offerings": _v1_wellness_offerings(report_data),
        "biorhythm": biorhythm_summary(report_data),
        "biorhythm_calendar": _v1_biorhythm_calendar(report_data),
        "dmit": _v1_dmit_summary(report_data),
    }


# ── Draft ID generation ─────────────────────────────────────────────

def _v1_draft_id(source_hash: str) -> str:
    """Generate a draft_id that doesn't collide with existing dirs."""
    return next_available_dir_id(DRAFTS_DIR, f"draft_{source_hash}")


def _v1_report_id(draft_id: str, source_hash: str) -> str:
    """Generate a final report_id from the draft/source hash."""
    base = f"report_{source_hash}" if source_hash else f"report_{draft_id.removeprefix('draft_')}"
    existing = REPORTS_DIR / base
    if not existing.exists():
        return base
    existing_meta = load_metadata(existing)
    if existing_meta.get("draft_report_id") == draft_id:
        return base
    return next_available_dir_id(REPORTS_DIR, base)


# ═════════════════════════════════════════════════════════════════════
# DOCTOR / INTEGRATION ENDPOINTS
# ═════════════════════════════════════════════════════════════════════

@router.post("/doctor/drafts", summary="Doctor upload: create a wellness draft")
@router.post("/reports/drafts", summary="Create a wellness report draft", include_in_schema=False)
async def v1_create_draft(
    ecg: UploadFile = File(..., description="ECG PDF report"),
    hrv: UploadFile = File(..., description="HRV PDF report"),
    nadi: UploadFile = File(..., description="Nadi Tarangini PDF report"),
    biowell: UploadFile = File(..., description="Bio-Well PDF report"),
    biores: UploadFile = File(..., description="Bioresonance PDF report"),
    inbody: UploadFile = File(..., description="InBody image (JPG/PNG)"),
    dmit: UploadFile = File(None, description="DMIT PDF report (optional)"),
    name: str = Form("", description="Patient name"),
    dob: str = Form("", description="Patient DOB (e.g. 1990-05-15 or 15/05/1990)"),
    patient_id: str = Form("", description="External patient ID (required)"),
    date: str = Form("", description="Report date (e.g. 2026-06-20)"),
    doctor_id: str = Form("", description="Doctor ID (alternative to X-Doctor-Id header)"),
    x_doctor_id: str | None = Header(None, alias="X-Doctor-Id"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Upload device files → extract/synthesize → save draft.

    **Idempotent**: same files + patient inputs return the existing draft
    (no re-extraction). Accepts ``X-Doctor-Id`` header or ``doctor_id`` field.
    """
    effective_doctor_id = x_doctor_id or doctor_id or ""
    if not patient_id:
        raise HTTPException(400, "patient_id is required")

    # ── Read + hash uploads ──────────────────────────────────────────
    normalized_dob = normalize_date_value(dob)
    normalized_date = normalize_date_value(date)
    files = await read_report_uploads(
        {"ecg": ecg, "hrv": hrv, "nadi": nadi, "biowell": biowell, "biores": biores, "inbody": inbody},
        dmit=dmit,
    )
    patient_inputs = {
        "name": name, "dob": normalized_dob,
        "patient_id": patient_id, "date": normalized_date,
    }
    file_hash = compute_file_hash(files, patient_inputs)

    # ── Idempotency-Key check ────────────────────────────────────────
    if idempotency_key:
        existing = draft_service.find_by_idempotency_key(idempotency_key)
        if existing:
            existing_source_hash = existing.get("source_hash") or ""
            if existing_source_hash != file_hash:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "idempotency_key_conflict",
                        "message": (
                            "Idempotency-Key was already used for a different draft request. "
                            "Use a new Idempotency-Key when files or patient inputs change."
                        ),
                        "existing_draft_id": existing.get("draft_id", ""),
                    },
                )
            draft_json = existing.get("draft_json")
            if isinstance(draft_json, str):
                draft_json = json.loads(draft_json)
            return {
                "draft_id": existing["draft_id"],
                "patient_id": existing["patient_id"],
                "status": existing["status"],
                "created_by_doctor_id": existing.get("doctor_id") or "",
                "report": _v1_public_report(apply_cached_recommendations(draft_json or {})),
                "cached": True,
                "idempotency_replay": True,
                "extraction_summary": existing.get("extraction_summary") or {},
            }

    # ── Source-hash idempotency (DB) ─────────────────────────────────
    existing_wf = draft_service.find_draft_by_source_hash(file_hash)
    if existing_wf:
        draft_json = existing_wf.get("draft_json")
        if isinstance(draft_json, str):
            draft_json = json.loads(draft_json)
        return {
            "draft_id": existing_wf["draft_id"],
            "patient_id": existing_wf["patient_id"],
            "status": existing_wf["status"],
            "created_by_doctor_id": existing_wf.get("doctor_id") or "",
            "report": _v1_public_report(apply_cached_recommendations(draft_json or {})),
            "cached": True,
            "existing_draft": True,
            "extraction_summary": existing_wf.get("extraction_summary") or {},
        }

    # ── Generate draft ───────────────────────────────────────────────
    draft_id = _v1_draft_id(file_hash)
    draft_dir = DRAFTS_DIR / draft_id

    cached = find_cached_report(file_hash)
    if cached:
        report_data = apply_cached_recommendations(read_json(cached["path"]))
        report_data = apply_patient_inputs(
            report_data, name=name, dob=normalized_dob,
            patient_id=patient_id, date=normalized_date,
        )
        image_path = report_data.get("biorhythm", {}).get("image_path")
        if image_path and Path(image_path).exists():
            draft_dir.mkdir(parents=True, exist_ok=True)
            draft_image = draft_dir / "biorhythm_graph.png"
            shutil.copy2(image_path, draft_image)
            report_data.setdefault("biorhythm", {})["image_path"] = str(draft_image)
        write_json(draft_dir / REPORT_JSON, report_data)
        extraction_sum = {}
    else:
        result = await synthesize_from_uploads(
            report_id=draft_id, report_dir=draft_dir, files=files,
            name=name, dob=normalized_dob, patient_id=patient_id, date=normalized_date,
        )
        report_data = result["report"]
        extraction_sum = result["extraction_summary"]

    # ── Persist metadata (file-based, for legacy compat) ─────────────
    write_metadata(draft_dir, {
        "draft_report_id": draft_id,
        "status": "draft",
        "source": "v1_draft",
        "source_hash": file_hash,
        "doctor_id": effective_doctor_id,
        "patient": patient_identity(report_data),
        "extraction_summary": extraction_sum,
    })

    # ── Persist to workflow DB ───────────────────────────────────────
    try:
        draft_service.create_draft(
            draft_id=draft_id,
            patient_id=patient_id,
            doctor_id=effective_doctor_id,
            source_hash=file_hash,
            draft_json=report_data,
            extraction_summary=extraction_sum,
            idempotency_key=idempotency_key or "",
        )
    except Exception as e:
        log.warning(f"[v1] DB draft insert failed (non-fatal, file-based fallback): {e}")

    return {
        "draft_id": draft_id,
        "patient_id": patient_id,
        "status": "draft",
        "created_by_doctor_id": effective_doctor_id,
        "report": _v1_public_report(report_data),
        "cached": bool(cached),
        "extraction_summary": extraction_sum,
    }


@router.get("/doctor/drafts/{draft_id}/dashboard", summary="Doctor draft dashboard")
@router.get("/doctor/drafts/{draft_id}", summary="Doctor draft detail")
@router.get("/reports/drafts/{draft_id}", summary="Get a draft report", include_in_schema=False)
async def v1_get_draft(draft_id: str):
    """Return the full draft report JSON + metadata for doctor review."""
    # Try DB first, fall back to file system
    wf = draft_service.get_by_draft_id(draft_id)
    if wf:
        draft_json = wf.get("draft_json")
        if isinstance(draft_json, str):
            draft_json = json.loads(draft_json)
        return {
            "draft_id": draft_id,
            "report_id": wf.get("report_id") or "",
            "patient_id": wf["patient_id"],
            "status": wf["status"],
            "created_by_doctor_id": wf.get("doctor_id") or "",
            "report": _v1_public_report(apply_cached_recommendations(draft_json or {})),
        }

    # File-based fallback
    draft_dir = DRAFTS_DIR / draft_id
    json_path = draft_dir / REPORT_JSON
    if not json_path.exists():
        raise HTTPException(404, f"Draft {draft_id} not found")
    metadata = load_metadata(draft_dir)
    return {
        "draft_id": draft_id,
        "report_id": metadata.get("approved_report_id", ""),
        "patient_id": metadata.get("patient", {}).get("id", ""),
        "status": metadata.get("status", "draft"),
        "created_by_doctor_id": metadata.get("doctor_id", ""),
        "report": _v1_public_report(apply_cached_recommendations(read_json(json_path))),
    }


@router.patch("/doctor/drafts/{draft_id}", summary="Doctor edit draft")
@router.patch("/reports/drafts/{draft_id}", summary="Edit a draft report", include_in_schema=False)
async def v1_patch_draft(
    draft_id: str,
    payload: dict = Body(...),
    x_doctor_id: str | None = Header(None, alias="X-Doctor-Id"),
):
    """Deep-merge updates into the draft JSON.

    No re-extraction, no re-synthesis, no PDF generation.
    Refreshes biorhythm calendar if DOB or date changed.
    """
    draft_dir = DRAFTS_DIR / draft_id
    json_path = draft_dir / REPORT_JSON
    if not json_path.exists():
        raise HTTPException(404, f"Draft {draft_id} not found")

    # Check status from DB or file
    wf = draft_service.get_by_draft_id(draft_id)
    status = (wf or {}).get("status") or load_metadata(draft_dir).get("status", "draft")
    if status != "draft":
        raise HTTPException(409, f"Draft {draft_id} is not editable (status={status})")

    report_data = read_json(json_path)
    updates = payload.get("report", payload)
    if not isinstance(updates, dict):
        raise HTTPException(400, "PATCH payload must be a JSON object")

    report_data = deep_merge(report_data, updates)
    report_data = refresh_biorhythm_calendar(report_data, draft_dir)
    write_json(json_path, report_data)
    write_metadata(draft_dir, {"patient": patient_identity(report_data)})

    # Sync to DB
    try:
        draft_service.update_draft_json(draft_id, report_data)
    except Exception as e:
        log.warning(f"[v1] DB draft update failed (non-fatal): {e}")

    return {
        "draft_id": draft_id,
        "status": "draft",
        "report": _v1_public_report(report_data),
    }


@router.post("/doctor/drafts/{draft_id}/approve", summary="Doctor approve draft")
@router.post("/reports/drafts/{draft_id}/approve", summary="Approve a draft report", include_in_schema=False)
async def v1_approve_draft(
    draft_id: str,
    x_doctor_id: str | None = Header(None, alias="X-Doctor-Id"),
):
    """Approve a draft → generate final PDF → save to history.

    **Idempotent**: if already approved, returns the existing approval.
    The response includes the full approved report so the doctor can
    review the final version immediately.
    """
    approving_doctor = x_doctor_id or ""

    # ── Check current state ──────────────────────────────────────────
    draft_dir = DRAFTS_DIR / draft_id
    draft_json_path = draft_dir / REPORT_JSON
    if not draft_json_path.exists():
        raise HTTPException(404, f"Draft {draft_id} not found")

    wf = draft_service.get_by_draft_id(draft_id)
    file_meta = load_metadata(draft_dir)
    current_status = (wf or {}).get("status") or file_meta.get("status", "draft")

    # ── Idempotent: already approved ─────────────────────────────────
    if current_status == "approved":
        report_id = (wf or {}).get("report_id") or file_meta.get("approved_report_id", "")
        if report_id:
            approved_json = (wf or {}).get("approved_json")
            if isinstance(approved_json, str):
                approved_json = json.loads(approved_json)
            if not approved_json:
                final_json = REPORTS_DIR / report_id / REPORT_JSON
                approved_json = read_json(final_json) if final_json.exists() else {}
            approved_json = apply_cached_recommendations(approved_json)
            return {
                "report_id": report_id,
                "draft_id": draft_id,
                "status": "approved",
                "created_by_doctor_id": (wf or {}).get("doctor_id") or file_meta.get("doctor_id", ""),
                "approved_by_doctor_id": (wf or {}).get("approved_by") or approving_doctor,
                "links": _v1_report_links(report_id, patient_identity(approved_json).get("id", ""), audience="all"),
                "download_requires": _v1_download_requires(),
                "report": _v1_public_report(approved_json),
                "summary": _v1_summary_payload(report_id, approved_json, audience="all"),
                "history": {},
            }
        raise HTTPException(409, f"Draft {draft_id} cannot be approved")

    if current_status != "draft":
        raise HTTPException(409, f"Draft {draft_id} is not approvable (status={current_status})")

    # ── Build report_id and final directory ───────────────────────────
    source_hash = (wf or {}).get("source_hash") or file_meta.get("source_hash", "")
    report_id = _v1_report_id(draft_id, source_hash)
    final_dir = REPORTS_DIR / report_id

    # Check if final dir already exists (race-condition guard)
    if final_dir.exists():
        final_meta = load_metadata(final_dir)
        if final_meta.get("status") == "approved" and pdf_path(report_id).exists():
            report_data = apply_cached_recommendations(read_json(final_dir / REPORT_JSON))
            # Update draft status
            write_metadata(draft_dir, {"status": "approved", "approved_report_id": report_id})
            try:
                draft_service.approve_draft(
                    draft_id=draft_id, report_id=report_id,
                    approved_by=approving_doctor, approved_json=report_data,
                    pdf_path=str(pdf_path(report_id)),
                )
            except Exception as e:
                log.warning(f"[v1] DB approve update failed: {e}")
            history_data = save_approved_history(report_id, report_data)
            return {
                "report_id": report_id,
                "draft_id": draft_id,
                "status": "approved",
                "created_by_doctor_id": (wf or {}).get("doctor_id") or file_meta.get("doctor_id", ""),
                "approved_by_doctor_id": approving_doctor,
                "links": _v1_report_links(report_id, patient_identity(report_data).get("id", ""), audience="all"),
                "download_requires": _v1_download_requires(),
                "report": _v1_public_report(report_data),
                "summary": _v1_summary_payload(report_id, report_data, audience="all"),
                "history": history_data,
            }
    else:
        shutil.copytree(draft_dir, final_dir)

    # ── Read draft, refresh biorhythm, generate PDF ──────────────────
    report_data = read_json(draft_json_path)
    report_data = refresh_biorhythm_calendar(report_data, final_dir)

    biorhythm = report_data.get("biorhythm", {})
    final_graph = final_dir / "biorhythm_graph.png"
    if final_graph.exists() and biorhythm.get("image_path"):
        biorhythm["image_path"] = str(final_graph)

    write_json(final_dir / REPORT_JSON, report_data)

    final_pdf = final_dir / REPORT_PDF
    try:
        await generate_pdf(report_data, str(final_pdf))
        log.info(f"[v1][{report_id}] Approved PDF generated")
    except Exception as e:
        log.error(f"[v1][{report_id}] PDF generation failed: {e}")
        raise HTTPException(500, f"PDF generation failed: {e}") from e

    # ── Update metadata (file-based) ─────────────────────────────────
    write_metadata(final_dir, {
        "report_id": report_id,
        "draft_report_id": draft_id,
        "status": "approved",
        "source": "v1_approval",
        "source_hash": source_hash,
        "doctor_id": (wf or {}).get("doctor_id") or file_meta.get("doctor_id", ""),
        "approved_by": approving_doctor,
        "patient": patient_identity(report_data),
    })
    write_metadata(draft_dir, {
        "status": "approved",
        "approved_report_id": report_id,
    })

    # ── Update hash index for legacy compat ──────────────────────────
    if source_hash:
        save_hash_index(source_hash, report_id)

    # ── Update workflow DB ───────────────────────────────────────────
    try:
        draft_service.approve_draft(
            draft_id=draft_id,
            report_id=report_id,
            approved_by=approving_doctor,
            approved_json=report_data,
            pdf_path=str(final_pdf),
        )
    except Exception as e:
        log.warning(f"[v1] DB approve failed (non-fatal): {e}")

    # ── Save approved history ────────────────────────────────────────
    history_data = save_approved_history(report_id, report_data)

    creating_doctor = (wf or {}).get("doctor_id") or file_meta.get("doctor_id", "")

    return {
        "report_id": report_id,
        "draft_id": draft_id,
        "status": "approved",
        "created_by_doctor_id": creating_doctor,
        "approved_by_doctor_id": approving_doctor,
        "links": _v1_report_links(report_id, patient_identity(report_data).get("id", ""), audience="all"),
        "download_requires": _v1_download_requires(),
        "report": _v1_public_report(report_data),
        "summary": _v1_summary_payload(report_id, report_data, audience="all"),
        "history": history_data,
    }


# ═════════════════════════════════════════════════════════════════════
# DOCTOR — PATIENT DRAFT QUERIES
# ═════════════════════════════════════════════════════════════════════

@router.get("/doctor/patients", summary="Doctor patient list")
async def v1_doctor_patients(limit: int = 100):
    """Doctor-only: list patients with workflow activity."""
    patients = draft_service.list_patients(limit=limit)
    return {"patients": patients, "total": len(patients)}


@router.get("/doctor/patients/{patient_id}/drafts", summary="Doctor patient draft/workflow list")
@router.get("/patients/{patient_id}/drafts", summary="List drafts for a patient", include_in_schema=False)
async def v1_patient_drafts(patient_id: str, limit: int = 20):
    """Doctor-only: list all drafts (any status) for a patient."""
    rows = draft_service.get_patient_drafts(patient_id, limit=limit)
    drafts = []
    for row in rows:
        draft_json = row.get("draft_json")
        if isinstance(draft_json, str):
            draft_json = json.loads(draft_json)
        drafts.append({
            "draft_id": row["draft_id"],
            "report_id": row.get("report_id") or "",
            "status": row["status"],
            "created_by_doctor_id": row.get("doctor_id") or "",
            "created_at": row.get("created_at", ""),
            "patient": patient_identity(draft_json or {}),
        })
    return {"patient_id": patient_id, "drafts": drafts, "total": len(drafts)}


@router.get("/doctor/patients/{patient_id}/active-draft", summary="Doctor patient active draft")
@router.get("/patients/{patient_id}/active-draft", summary="Get active draft for a patient", include_in_schema=False)
async def v1_patient_active_draft(patient_id: str):
    """Doctor-only: return the latest draft with status='draft'."""
    row = draft_service.get_active_draft(patient_id)
    if not row:
        raise HTTPException(404, f"No active draft for patient {patient_id}")
    draft_json = row.get("draft_json")
    if isinstance(draft_json, str):
        draft_json = json.loads(draft_json)
    return {
        "draft_id": row["draft_id"],
        "patient_id": patient_id,
        "status": "draft",
        "created_by_doctor_id": row.get("doctor_id") or "",
        "report": _v1_public_report(apply_cached_recommendations(draft_json or {})),
    }


# ═════════════════════════════════════════════════════════════════════
# USER / CUSTOMER ENDPOINTS (approved only — no drafts exposed)
# ═════════════════════════════════════════════════════════════════════

def _v1_patient_report_list(patient_id: str, limit: int, audience: str) -> dict:
    """Build an approved report list. Drafts are never included."""
    rows = draft_service.get_approved_reports(patient_id, limit=limit)
    reports = []
    for row in rows:
        approved_json = row.get("approved_json")
        if isinstance(approved_json, str):
            approved_json = json.loads(approved_json)
        if approved_json:
            report_id = row.get("report_id") or ""
            if report_id:
                reports.append(_v1_summary_payload(report_id, approved_json, audience=audience))
    return {"patient_id": patient_id, "reports": reports, "total": len(reports)}


@router.get("/doctor/patients/{patient_id}/reports", summary="Doctor patient approved reports")
async def v1_doctor_patient_reports(patient_id: str, limit: int = 20):
    """Doctor-side approved report list for one patient."""
    return _v1_patient_report_list(patient_id, limit, audience="doctor")


@router.get("/patients/{patient_id}/reports", summary="Patient report list")
async def v1_patient_reports(patient_id: str, limit: int = 20):
    """Patient-side approved report list."""
    return _v1_patient_report_list(patient_id, limit, audience="patient")


@router.get("/patients/{patient_id}/history", summary="Patient chart history")
async def v1_patient_history(patient_id: str, limit: int = 20):
    """Return chart/trend history only. No report cards or draft data."""
    try:
        history = get_chart_data(patient_id, limit=limit)
    except Exception as e:
        log.warning(f"[v1] Patient history unavailable for {patient_id}: {e}")
        history = {"dates": [], "stats": {}, "dimensions": {}, "systems": {}, "visit_count": 0}
    return {"patient_id": patient_id, "history": history}


@router.get("/patients/{patient_id}/dashboard", summary="Patient dashboard")
async def v1_patient_dashboard(
    patient_id: str,
    limit: int = 10,
):
    """User/customer dashboard: latest report summary + chart history."""
    rows = draft_service.get_approved_reports(patient_id, limit=limit)

    patient = {"id": patient_id, "name": "", "dob": ""}
    latest_payload = None
    reports = []

    for row in rows:
        approved_json = row.get("approved_json")
        if isinstance(approved_json, str):
            approved_json = json.loads(approved_json)
        if not approved_json:
            continue
        report_id = row.get("report_id") or ""
        if not report_id:
            continue
        payload = _v1_summary_payload(report_id, approved_json, audience="patient")
        reports.append(payload)
        if not latest_payload:
            latest_payload = payload
            p = approved_json.get("patient", {})
            patient = {
                "id": patient_id,
                "name": p.get("name", ""),
                "dob": p.get("dob", ""),
            }

    try:
        history = get_chart_data(patient_id, limit=limit)
    except Exception as e:
        log.warning(f"[v1] Dashboard history unavailable for {patient_id}: {e}")
        history = {"dates": [], "stats": {}, "dimensions": {}, "systems": {}, "visit_count": 0}

    return {
        "patient_id": patient_id,
        "patient": patient,
        "latest_report": latest_payload,
        "history": history,
        "reports": reports,
    }


def _assert_patient_report(patient_id: str, payload: dict):
    payload_patient_id = payload.get("patient_id") or payload.get("summary", {}).get("patient_id", "")
    if not payload_patient_id or payload_patient_id != patient_id:
        raise HTTPException(404, f"Approved report {payload.get('report_id', '')} not found for patient {patient_id}")


@router.get("/doctor/reports/{report_id}", summary="Doctor final report")
@router.get("/reports/{report_id}", summary="Get an approved report", include_in_schema=False)
async def v1_get_report(report_id: str, detail: str = "full"):
    """Return the full approved report JSON."""
    wf = draft_service.get_by_report_id(report_id)
    if wf:
        approved_json = wf.get("approved_json")
        if isinstance(approved_json, str):
            approved_json = json.loads(approved_json)
        if approved_json:
            approved_json = apply_cached_recommendations(approved_json)
            return {
                "report_id": report_id,
                "patient_id": wf.get("patient_id", ""),
                "status": "approved",
                "created_by_doctor_id": wf.get("doctor_id") or "",
                "approved_by_doctor_id": wf.get("approved_by") or "",
                "links": _v1_report_links(report_id, wf.get("patient_id", "")),
                "download_requires": _v1_download_requires(),
                "summary": _v1_summary_payload(report_id, approved_json),
                "detail": detail,
                "report": _v1_public_report(approved_json),
            }

    # File-based fallback
    json_path = REPORTS_DIR / report_id / REPORT_JSON
    if not json_path.exists():
        raise HTTPException(404, f"Report {report_id} not found")
    metadata = load_metadata(REPORTS_DIR / report_id)
    if metadata.get("status") not in (None, "", "approved"):
        raise HTTPException(404, f"Approved report {report_id} not found")
    report_data = apply_cached_recommendations(read_json(json_path))
    return {
        "report_id": report_id,
        "patient_id": metadata.get("patient", {}).get("id", ""),
        "status": "approved",
        "links": _v1_report_links(report_id, metadata.get("patient", {}).get("id", "")),
        "download_requires": _v1_download_requires(),
        "summary": _v1_summary_payload(report_id, report_data),
        "detail": detail,
        "report": _v1_public_report(report_data),
    }


@router.get("/patients/{patient_id}/reports/{report_id}", summary="Patient final report")
async def v1_get_patient_report(patient_id: str, report_id: str, detail: str = "full"):
    """Return one approved report for a specific patient."""
    payload = await v1_get_report(report_id, detail=detail)
    _assert_patient_report(patient_id, payload)
    payload["links"] = _v1_report_links(report_id, patient_id, audience="patient")
    if isinstance(payload.get("summary"), dict):
        payload["summary"]["links"] = _v1_report_links(report_id, patient_id, audience="patient")
    return payload


@router.get("/doctor/reports/{report_id}/summary", summary="Doctor report summary")
@router.get("/reports/{report_id}/summary", summary="Get report summary", include_in_schema=False)
async def v1_get_report_summary(report_id: str):
    """Compact summary for web/mobile dashboards."""
    wf = draft_service.get_by_report_id(report_id)
    if wf:
        approved_json = wf.get("approved_json")
        if isinstance(approved_json, str):
            approved_json = json.loads(approved_json)
        if approved_json:
            return _v1_summary_payload(report_id, approved_json)

    # File-based fallback
    json_path = REPORTS_DIR / report_id / REPORT_JSON
    if not json_path.exists():
        raise HTTPException(404, f"Report {report_id} not found")
    report_data = apply_cached_recommendations(read_json(json_path))
    return _v1_summary_payload(report_id, report_data)


@router.get("/patients/{patient_id}/reports/{report_id}/summary", summary="Patient report summary")
async def v1_get_patient_report_summary(patient_id: str, report_id: str):
    """Return one compact approved report summary for a specific patient."""
    payload = await v1_get_report_summary(report_id)
    _assert_patient_report(patient_id, payload)
    payload["links"] = _v1_report_links(report_id, patient_id, audience="patient")
    return payload


@router.get("/doctor/reports/{report_id}/pdf", summary="Doctor report PDF download")
@router.get("/reports/{report_id}/pdf", summary="Download report PDF", include_in_schema=False)
async def v1_get_report_pdf(report_id: str):
    """Download the approved report PDF."""
    p = pdf_path(report_id)
    if not p.exists():
        raise HTTPException(404, f"PDF for report {report_id} not found")
    return FileResponse(
        path=str(p),
        media_type="application/pdf",
        filename=f"wellness_report_{report_id}.pdf",
    )


@router.get("/patients/{patient_id}/reports/{report_id}/pdf", summary="Patient report PDF download")
async def v1_get_patient_report_pdf(patient_id: str, report_id: str):
    """Download one approved report PDF for a specific patient."""
    await v1_get_patient_report_summary(patient_id, report_id)
    return await v1_get_report_pdf(report_id)
