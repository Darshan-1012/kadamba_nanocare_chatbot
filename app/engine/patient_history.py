"""Patient history — stores all 32 report metrics per visit in MySQL `nano` DB.

Tracks across visits:
  - 8 stats-bar values  (weight, visceral_fat, bmi, heart_rate, bio_energy,
                          energy_reserve, lf_hf_ratio, nadi_pulse)
  - 4 dimension scores  (physical, psychological, emotional, spiritual)
  - 10 body-system scores + statuses

Used by the API to serve patient progress history for mobile/web charting.
"""
import logging
from datetime import datetime

from app.db.db_utils import execute_query, execute_write, get_cursor

log = logging.getLogger(__name__)

# ── Table DDL ────────────────────────────────────────────────────────
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS wellness_report_history (
    id                          INT AUTO_INCREMENT PRIMARY KEY,
    patient_id                  VARCHAR(50)  NOT NULL,
    visit_date                  DATE         NOT NULL,
    report_hash                 VARCHAR(32)  NOT NULL,

    -- Stats Bar (8 metrics)
    weight                      DECIMAL(6,2),
    visceral_fat                DECIMAL(5,2),
    bmi                         DECIMAL(5,2),
    heart_rate                  INT,
    bio_energy                  DECIMAL(6,2),
    energy_reserve              INT,
    lf_hf_ratio                 DECIMAL(5,2),
    nadi_pulse                  INT,

    -- Dimension Scores (4 × 0-100)
    score_physical              INT,
    score_psychological         INT,
    score_emotional             INT,
    score_spiritual             INT,

    -- Body System Scores + Statuses (10 systems)
    sys_nervous                 INT,
    sys_nervous_status          VARCHAR(20),
    sys_cardiovascular          INT,
    sys_cardiovascular_status   VARCHAR(20),
    sys_respiratory             INT,
    sys_respiratory_status      VARCHAR(20),
    sys_musculoskeletal         INT,
    sys_musculoskeletal_status  VARCHAR(20),
    sys_digestive               INT,
    sys_digestive_status        VARCHAR(20),
    sys_integumentary           INT,
    sys_integumentary_status    VARCHAR(20),
    sys_endocrine               INT,
    sys_endocrine_status        VARCHAR(20),
    sys_urogenital              INT,
    sys_urogenital_status       VARCHAR(20),
    sys_reproductive            INT,
    sys_reproductive_status     VARCHAR(20),
    sys_immune                  INT,
    sys_immune_status           VARCHAR(20),

    -- Full report JSON (for drill-down)
    report_json                 JSON,
    created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_patient_visit (patient_id, report_hash),
    INDEX idx_patient_date      (patient_id, visit_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ── Column lists (order must match INSERT placeholders) ──────────────
_STAT_COLS = [
    "weight", "visceral_fat", "bmi", "heart_rate",
    "bio_energy", "energy_reserve", "lf_hf_ratio", "nadi_pulse",
]

_DIM_COLS = [
    "score_physical", "score_psychological",
    "score_emotional", "score_spiritual",
]

_SYSTEM_KEYS = [
    "nervous", "cardiovascular", "respiratory", "musculoskeletal",
    "digestive", "integumentary", "endocrine", "urogenital",
    "reproductive", "immune",
]


def _safe_num(val, fallback=None):
    """Safely convert a value to a number, returning fallback on failure."""
    if val is None:
        return fallback
    try:
        return float(val) if "." in str(val) else int(val)
    except (ValueError, TypeError):
        return fallback


# ── Public API ───────────────────────────────────────────────────────

def ensure_table():
    """Create the wellness_report_history table if it doesn't exist."""
    try:
        execute_write(_CREATE_TABLE_SQL)
        log.info("wellness_report_history table ready")
    except Exception as e:
        log.error(f"Failed to create wellness_report_history table: {e}")
        raise


def save_visit(
    patient_id: str,
    visit_date: str,
    report_hash: str,
    report_data: dict,
) -> bool:
    """Extract all 32 metrics from report_data and persist to MySQL.

    Idempotent: uses ON DUPLICATE KEY UPDATE on (patient_id, report_hash).
    Returns True on success, False on failure.
    """
    try:
        # Parse visit_date to a proper DATE value
        date_val = _parse_date(visit_date)

        # Extract metrics from the report dict
        metrics = report_data.get("metrics", {})
        dimensions = report_data.get("dimensions", {})
        systems = report_data.get("systems", {})

        # Build row values
        row = {
            "patient_id": patient_id,
            "visit_date": date_val,
            "report_hash": report_hash,
            # Stats bar
            "weight": _safe_num(metrics.get("weight")),
            "visceral_fat": _safe_num(metrics.get("visceralFat")),
            "bmi": _safe_num(metrics.get("bmi")),
            "heart_rate": _safe_num(metrics.get("heartRate")),
            "bio_energy": _safe_num(metrics.get("bioEnergy")),
            "energy_reserve": _safe_num(metrics.get("energyReserve")),
            "lf_hf_ratio": _safe_num(metrics.get("lfhfRatio")),
            "nadi_pulse": _safe_num(metrics.get("nadiPulse")),
            # Dimension scores
            "score_physical": _safe_num(dimensions.get("physical", {}).get("score")),
            "score_psychological": _safe_num(dimensions.get("psychological", {}).get("score")),
            "score_emotional": _safe_num(dimensions.get("emotional", {}).get("score")),
            "score_spiritual": _safe_num(dimensions.get("spiritual", {}).get("score")),
        }

        # System scores + statuses (10 systems × 2 cols each)
        for sys_key in _SYSTEM_KEYS:
            sys_data = systems.get(sys_key, {})
            row[f"sys_{sys_key}"] = _safe_num(sys_data.get("score"))
            row[f"sys_{sys_key}_status"] = sys_data.get("displayStatus") or sys_data.get("status")

        # Full report JSON (stored for drill-down)
        import json
        row["report_json"] = json.dumps(report_data, ensure_ascii=False)

        # Build the INSERT ... ON DUPLICATE KEY UPDATE statement
        cols = list(row.keys())
        placeholders = ", ".join([f"%({c})s" for c in cols])
        update_clause = ", ".join(
            [f"{c} = VALUES({c})" for c in cols if c not in ("patient_id", "report_hash")]
        )

        sql = f"""
            INSERT INTO wellness_report_history ({', '.join(cols)})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {update_clause}
        """
        execute_write(sql, row)
        log.info(f"[History] Saved visit for patient={patient_id}, date={date_val}, hash={report_hash}")
        return True

    except Exception as e:
        log.error(f"[History] Failed to save visit for patient={patient_id}: {e}")
        return False


def get_history(patient_id: str, limit: int = 10) -> list[dict]:
    """Return all visits for a patient, most recent first."""
    sql = """
        SELECT * FROM wellness_report_history
        WHERE patient_id = %s
        ORDER BY visit_date DESC
        LIMIT %s
    """
    rows = execute_query(sql, (patient_id, limit))
    # Convert date/decimal types for JSON serialization
    return [_serialize_row(r) for r in rows]


def get_chart_data(patient_id: str, limit: int = 10) -> dict:
    """Return chart-ready arrays for frontend charting.

    Returns:
        {
            "dates": ["2026-01-15", ...],
            "stats": {"weight": [88.2, ...], ...},
            "dimensions": {"physical": [72, ...], ...},
            "systems": {"nervous": [{"score": 80, "status": "Normal"}, ...], ...},
            "visit_count": 3
        }
    """
    sql = """
        SELECT * FROM wellness_report_history
        WHERE patient_id = %s
        ORDER BY visit_date ASC
        LIMIT %s
    """
    rows = execute_query(sql, (patient_id, limit))

    if not rows:
        return {"dates": [], "stats": {}, "dimensions": {}, "systems": {}, "visit_count": 0}

    dates = []
    stats = {col: [] for col in _STAT_COLS}
    dims = {d.replace("score_", ""): [] for d in _DIM_COLS}
    systems = {sk: [] for sk in _SYSTEM_KEYS}

    for row in rows:
        dates.append(str(row["visit_date"]))

        # Stats
        for col in _STAT_COLS:
            val = row.get(col)
            stats[col].append(float(val) if val is not None else None)

        # Dimensions
        for dcol in _DIM_COLS:
            dim_name = dcol.replace("score_", "")
            val = row.get(dcol)
            dims[dim_name].append(int(val) if val is not None else None)

        # Systems (score + status per visit)
        for sk in _SYSTEM_KEYS:
            score_val = row.get(f"sys_{sk}")
            status_val = row.get(f"sys_{sk}_status")
            systems[sk].append({
                "score": int(score_val) if score_val is not None else None,
                "status": status_val,
            })

    return {
        "dates": dates,
        "stats": stats,
        "dimensions": dims,
        "systems": systems,
        "visit_count": len(rows),
    }


def get_latest_visit(patient_id: str) -> dict | None:
    """Return the most recent visit for a patient, or None."""
    rows = get_history(patient_id, limit=1)
    return rows[0] if rows else None


# ── Helpers ──────────────────────────────────────────────────────────

def _parse_date(date_str: str) -> str:
    """Parse various date formats to YYYY-MM-DD."""
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")

    # Try common formats
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d-%m-%Y", "%d/%m/%Y", "%B %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Fallback: today
    log.warning(f"[History] Could not parse date '{date_str}', using today")
    return datetime.now().strftime("%Y-%m-%d")


def _serialize_row(row: dict) -> dict:
    """Convert MySQL row types to JSON-safe values."""
    import decimal
    from datetime import date, datetime as dt

    out = {}
    for k, v in row.items():
        if k == "report_json":
            continue  # skip large blob in list views
        elif isinstance(v, decimal.Decimal):
            out[k] = float(v)
        elif isinstance(v, (date, dt)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out
