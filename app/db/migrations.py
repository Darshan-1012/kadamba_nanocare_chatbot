"""Database migrations for the Nanocare Wellness API.

All migrations are idempotent — safe to run on every server startup.
"""
import logging

from app.db.db_utils import execute_write, get_cursor

log = logging.getLogger(__name__)

# ── wellness_report_workflow table DDL ────────────────────────────────
_CREATE_WORKFLOW_TABLE = """
CREATE TABLE IF NOT EXISTS wellness_report_workflow (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    draft_id            VARCHAR(64)  NOT NULL UNIQUE,
    report_id           VARCHAR(64),
    source_hash         VARCHAR(32)  NOT NULL,
    patient_id          VARCHAR(50)  NOT NULL,
    doctor_id           VARCHAR(50),
    approved_by         VARCHAR(50),
    idempotency_key     VARCHAR(128),
    status              ENUM('draft','approved','rejected') DEFAULT 'draft',
    draft_json          JSON,
    approved_json       JSON,
    pdf_path            VARCHAR(255),
    extraction_summary  JSON,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    approved_at         TIMESTAMP NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ── Column additions (safe if already present) ───────────────────────
_ADD_COLUMNS = [
    "ALTER TABLE wellness_report_workflow ADD COLUMN doctor_id VARCHAR(50) AFTER patient_id",
    "ALTER TABLE wellness_report_workflow ADD COLUMN approved_by VARCHAR(50) AFTER doctor_id",
    "ALTER TABLE wellness_report_workflow ADD COLUMN idempotency_key VARCHAR(128) AFTER approved_by",
]

# ── Index additions ──────────────────────────────────────────────────
_ADD_INDEXES = [
    ("idx_wf_patient_status", "CREATE INDEX idx_wf_patient_status ON wellness_report_workflow (patient_id, status)"),
    ("idx_wf_patient_created_at", "CREATE INDEX idx_wf_patient_created_at ON wellness_report_workflow (patient_id, created_at, id)"),
    ("idx_wf_patient_status_created_at", "CREATE INDEX idx_wf_patient_status_created_at ON wellness_report_workflow (patient_id, status, created_at, id)"),
    ("idx_wf_patient_status_approved_at", "CREATE INDEX idx_wf_patient_status_approved_at ON wellness_report_workflow (patient_id, status, approved_at, id)"),
    ("idx_wf_source_hash", "CREATE INDEX idx_wf_source_hash ON wellness_report_workflow (source_hash, status)"),
    ("idx_wf_idempotency", "CREATE INDEX idx_wf_idempotency ON wellness_report_workflow (idempotency_key)"),
    ("idx_wf_report_id", "CREATE INDEX idx_wf_report_id ON wellness_report_workflow (report_id)"),
]


def _column_exists(table: str, column: str) -> bool:
    """Check if a column already exists in a table."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
            (table, column),
        )
        row = cur.fetchone()
        return bool(row and row.get("cnt", 0) > 0)


def _index_exists(table: str, index_name: str) -> bool:
    """Check if an index already exists on a table."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s",
            (table, index_name),
        )
        row = cur.fetchone()
        return bool(row and row.get("cnt", 0) > 0)


def run_migrations():
    """Run all idempotent migrations for the wellness workflow tables.

    Safe to call on every server startup.
    """
    # 1. Create table if it doesn't exist
    try:
        execute_write(_CREATE_WORKFLOW_TABLE)
        log.info("wellness_report_workflow table ready")
    except Exception as e:
        log.error(f"Failed to create wellness_report_workflow table: {e}")
        raise

    # 2. Add columns if missing (for existing installations)
    column_map = {
        "doctor_id": _ADD_COLUMNS[0],
        "approved_by": _ADD_COLUMNS[1],
        "idempotency_key": _ADD_COLUMNS[2],
    }
    for col_name, alter_sql in column_map.items():
        if not _column_exists("wellness_report_workflow", col_name):
            try:
                execute_write(alter_sql)
                log.info(f"Added column {col_name} to wellness_report_workflow")
            except Exception as e:
                log.warning(f"Column {col_name} add skipped: {e}")

    # 3. Add indexes if missing
    for idx_name, create_sql in _ADD_INDEXES:
        if not _index_exists("wellness_report_workflow", idx_name):
            try:
                execute_write(create_sql)
                log.info(f"Created index {idx_name}")
            except Exception as e:
                log.warning(f"Index {idx_name} creation skipped: {e}")

    log.info("All wellness workflow migrations complete")
