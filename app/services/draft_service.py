"""Draft lifecycle service — all MySQL operations for wellness_report_workflow.

Provides a clean data-access layer so route handlers never write raw SQL.
All functions are synchronous (pymysql is blocking).
"""
import json
import logging
from datetime import datetime

from app.db.db_utils import execute_query, execute_write

log = logging.getLogger(__name__)


# ── Data classes (plain dicts for now) ────────────────────────────────

def _serialize_row(row: dict) -> dict:
    """Convert MySQL types to JSON-safe values."""
    import decimal
    from datetime import date, datetime as dt

    out = {}
    for k, v in row.items():
        if isinstance(v, decimal.Decimal):
            out[k] = float(v)
        elif isinstance(v, (date, dt)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _bounded_limit(limit: int, *, default: int = 20, maximum: int = 100) -> int:
    """Keep patient history queries from accidentally requesting huge result sets."""
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def _fetch_rows_by_ids(ids: list[int]) -> list[dict]:
    """Fetch full workflow rows and preserve the caller's ID order."""
    if not ids:
        return []

    placeholders = ", ".join(["%s"] * len(ids))
    rows = execute_query(
        f"SELECT * FROM wellness_report_workflow WHERE id IN ({placeholders})",
        tuple(ids),
    )
    rows_by_id = {row["id"]: row for row in rows}
    return [rows_by_id[row_id] for row_id in ids if row_id in rows_by_id]


# ── Lookups ──────────────────────────────────────────────────────────

def find_draft_by_source_hash(
    source_hash: str,
    *,
    status: str = "draft",
) -> dict | None:
    """Find an existing workflow row matching source_hash + status."""
    rows = execute_query(
        "SELECT * FROM wellness_report_workflow "
        "WHERE source_hash = %s AND status = %s "
        "ORDER BY created_at DESC LIMIT 1",
        (source_hash, status),
    )
    return _serialize_row(rows[0]) if rows else None


def find_by_idempotency_key(key: str) -> dict | None:
    """Find a workflow row by idempotency key."""
    if not key:
        return None
    rows = execute_query(
        "SELECT * FROM wellness_report_workflow "
        "WHERE idempotency_key = %s LIMIT 1",
        (key,),
    )
    return _serialize_row(rows[0]) if rows else None


def get_by_draft_id(draft_id: str) -> dict | None:
    """Fetch a single workflow row by draft_id."""
    rows = execute_query(
        "SELECT * FROM wellness_report_workflow WHERE draft_id = %s LIMIT 1",
        (draft_id,),
    )
    return _serialize_row(rows[0]) if rows else None


def get_by_report_id(report_id: str) -> dict | None:
    """Fetch a single approved workflow row by report_id."""
    rows = execute_query(
        "SELECT * FROM wellness_report_workflow "
        "WHERE report_id = %s AND status = 'approved' LIMIT 1",
        (report_id,),
    )
    return _serialize_row(rows[0]) if rows else None


# ── Mutations ────────────────────────────────────────────────────────

def create_draft(
    *,
    draft_id: str,
    patient_id: str,
    doctor_id: str = "",
    source_hash: str,
    draft_json: dict,
    extraction_summary: dict | None = None,
    idempotency_key: str = "",
) -> dict:
    """Insert a new draft row into wellness_report_workflow."""
    sql = """
        INSERT INTO wellness_report_workflow
            (draft_id, patient_id, doctor_id, source_hash, status,
             draft_json, extraction_summary, idempotency_key)
        VALUES (%s, %s, %s, %s, 'draft', %s, %s, %s)
    """
    execute_write(sql, (
        draft_id,
        patient_id,
        doctor_id or None,
        source_hash,
        json.dumps(draft_json, ensure_ascii=False),
        json.dumps(extraction_summary or {}, ensure_ascii=False),
        idempotency_key or None,
    ))
    log.info(f"[DraftService] Created draft {draft_id} for patient {patient_id}")
    return get_by_draft_id(draft_id)


def update_draft_json(draft_id: str, updated_json: dict) -> dict:
    """Update the draft_json column for an existing draft."""
    execute_write(
        "UPDATE wellness_report_workflow "
        "SET draft_json = %s WHERE draft_id = %s AND status = 'draft'",
        (json.dumps(updated_json, ensure_ascii=False), draft_id),
    )
    log.info(f"[DraftService] Updated draft_json for {draft_id}")
    return get_by_draft_id(draft_id)


def approve_draft(
    *,
    draft_id: str,
    report_id: str,
    approved_by: str = "",
    approved_json: dict,
    pdf_path: str = "",
) -> dict:
    """Mark a draft as approved, setting all approval fields."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    execute_write(
        "UPDATE wellness_report_workflow "
        "SET status = 'approved', report_id = %s, approved_by = %s, "
        "    approved_json = %s, pdf_path = %s, approved_at = %s "
        "WHERE draft_id = %s AND status = 'draft'",
        (
            report_id,
            approved_by or None,
            json.dumps(approved_json, ensure_ascii=False),
            pdf_path or None,
            now,
            draft_id,
        ),
    )
    log.info(f"[DraftService] Approved draft {draft_id} -> report {report_id}")
    return get_by_draft_id(draft_id)


# ── Patient-scoped queries ───────────────────────────────────────────

def get_patient_drafts(
    patient_id: str,
    *,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Return workflow rows for a patient, optionally filtered by status."""
    limit = _bounded_limit(limit)
    if status:
        id_rows = execute_query(
            "SELECT id FROM wellness_report_workflow "
            "FORCE INDEX (idx_wf_patient_status_created_at) "
            "WHERE patient_id = %s AND status = %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (patient_id, status, limit),
        )
    else:
        id_rows = execute_query(
            "SELECT id FROM wellness_report_workflow "
            "FORCE INDEX (idx_wf_patient_created_at) "
            "WHERE patient_id = %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (patient_id, limit),
        )
    rows = _fetch_rows_by_ids([row["id"] for row in id_rows])
    return [_serialize_row(r) for r in rows]


def get_active_draft(patient_id: str) -> dict | None:
    """Return the latest draft with status='draft' for a patient."""
    id_rows = execute_query(
        "SELECT id FROM wellness_report_workflow "
        "FORCE INDEX (idx_wf_patient_status_created_at) "
        "WHERE patient_id = %s AND status = 'draft' "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        (patient_id,),
    )
    rows = _fetch_rows_by_ids([row["id"] for row in id_rows])
    return _serialize_row(rows[0]) if rows else None


def get_approved_reports(
    patient_id: str,
    *,
    limit: int = 20,
) -> list[dict]:
    """Return approved workflow rows for a patient, most recent first."""
    limit = _bounded_limit(limit)
    id_rows = execute_query(
        "SELECT id FROM wellness_report_workflow "
        "FORCE INDEX (idx_wf_patient_status_approved_at) "
        "WHERE patient_id = %s AND status = 'approved' "
        "ORDER BY approved_at DESC, id DESC LIMIT %s",
        (patient_id, limit),
    )
    rows = _fetch_rows_by_ids([row["id"] for row in id_rows])
    return [_serialize_row(r) for r in rows]


def list_patients(*, limit: int = 100) -> list[dict]:
    """Return patients that have workflow activity, newest activity first."""
    limit = _bounded_limit(limit, default=100, maximum=500)
    rows = execute_query(
        "SELECT patient_id, "
        "COUNT(*) AS workflow_count, "
        "SUM(status = 'draft') AS draft_count, "
        "SUM(status = 'approved') AS approved_count, "
        "MAX(created_at) AS latest_activity "
        "FROM wellness_report_workflow "
        "GROUP BY patient_id "
        "ORDER BY latest_activity DESC LIMIT %s",
        (limit,),
    )
    return [_serialize_row(r) for r in rows]
