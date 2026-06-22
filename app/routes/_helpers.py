"""Shared helper functions re-exported from the legacy report module.

This module provides clean public names for utility functions that both
the legacy ``report.py`` routes and the new ``wellness_v1.py`` routes need.
Importing from here (instead of ``report.py`` directly) keeps v1 code
decoupled from legacy underscore-prefixed internals.
"""

from app.routes.report import (  # noqa: F401 – re-exports
    # ── Constants ─────────────────────────────────────────────────────
    DRAFTS_DIR,
    REPORT_JSON,
    REPORT_META_JSON,
    REPORT_PDF,
    # ── Date / patient helpers ────────────────────────────────────────
    _normalize_date_value as normalize_date_value,
    _normalize_patient_dates as normalize_patient_dates,
    _apply_patient_inputs as apply_patient_inputs,
    _patient_identity as patient_identity,
    # ── JSON / metadata I/O ──────────────────────────────────────────
    _read_json as read_json,
    _write_json as write_json,
    _metadata_path as metadata_path,
    _load_metadata as load_metadata,
    _write_metadata as write_metadata,
    # ── File hash / cache ────────────────────────────────────────────
    _compute_file_hash as compute_file_hash,
    _find_cached_report as find_cached_report,
    _save_hash_index as save_hash_index,
    # ── PDF path ─────────────────────────────────────────────────────
    _pdf_path as pdf_path,
    # ── Report data transforms ───────────────────────────────────────
    _repair_unavailable_dimension_descriptions as repair_unavailable_dimension_descriptions,
    _apply_cached_recommendations as apply_cached_recommendations,
    _deep_merge as deep_merge,
    _refresh_biorhythm_calendar as refresh_biorhythm_calendar,
    # ── Upload processing ────────────────────────────────────────────
    _read_report_uploads as read_report_uploads,
    _stage_device_inputs as stage_device_inputs,
    _extraction_summary as extraction_summary,
    _synthesize_from_uploads as synthesize_from_uploads,
    # ── Summary builders ─────────────────────────────────────────────
    _domain_scores as domain_scores,
    _key_metrics as key_metrics,
    _wellness_summary as wellness_summary,
    _biorhythm_summary as biorhythm_summary,
    _report_summary_payload as report_summary_payload,
    # ── Approved report helpers ──────────────────────────────────────
    _save_approved_history as save_approved_history,
    _load_approved_report as load_approved_report,
    _approved_report_dirs as approved_report_dirs,
    # ── Draft / report ID helpers ────────────────────────────────────
    _next_available_dir_id as next_available_dir_id,
    _draft_report_id_for_source_hash as draft_report_id_for_source_hash,
    _final_report_id_for_draft as final_report_id_for_draft,
    _find_draft_by_source_hash as find_draft_by_source_hash,
    _generated_report_url as generated_report_url,
)

from app.config import REPORTS_DIR  # noqa: F401
