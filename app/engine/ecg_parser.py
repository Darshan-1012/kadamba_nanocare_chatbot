"""ECG + HRV PDF parser — extracts cardiac parameters directly, no LLM.

Parses Spandan device PDFs (ECG report and HRV report) to extract:
  ECG:  Heart rate, PR/QRS/QT/QTc intervals, rhythm, overall evaluation
  HRV:  SDNN, RMSSD, NN50, LF power, HF power, LF/HF ratio, stress coping

Both PDFs share the same Spandan table layout for ECG intervals.
Same PDF → same values, always.
"""
import logging
import re
from dataclasses import dataclass

# pyrefly: ignore [missing-import]
import pdfplumber

log = logging.getLogger(__name__)


@dataclass
class EcgResult:
    """Merged result from ECG + HRV PDFs."""
    patient_name: str = ""
    patient_age: str = ""
    scan_date: str = ""
    # ECG intervals
    heart_rate_bpm: int = 0
    pr_interval_ms: int = 0
    qrs_interval_ms: int = 0
    qt_interval_ms: int = 0
    qtc_interval_ms: int = 0
    rhythm: str = ""
    overall_evaluation: str = ""
    # HRV time-domain
    sdnn_ms: float = 0.0
    rmssd_ms: float = 0.0
    nn50: float = 0.0
    # HRV frequency-domain
    lf_power: float = 0.0
    hf_power: float = 0.0
    lf_hf_ratio: float = 0.0
    # HRV analysis
    stress_coping: str = ""
    stress_analysis: str = ""
    hrv_analysis: str = ""
    # Computed scores
    hr_score: int = 0
    qtc_score: int = 0
    rhythm_score: int = 0
    hrv_score: int = 0
    lf_hf_score: int = 0
    cardiovascular_score: int = 0


# ── Scoring rubrics ──────────────────────────────────────────────────

HR_RANGES = {
    (0, 50): 55, (50, 60): 75, (60, 100): 90,
    (100, 120): 65, (120, 300): 40,
}
QTC_RANGES = {
    (0, 250): 50, (250, 300): 65, (300, 450): 90,
    (450, 500): 55, (500, 999): 35,
}
SDNN_RANGES = {
    (0, 20): 40, (20, 50): 65, (50, 100): 90,
    (100, 200): 85, (200, 999): 80,
}
LF_HF_RANGES = {
    (0.0, 0.5): 50, (0.5, 0.8): 70, (0.8, 2.5): 85,
    (2.5, 4.0): 60, (4.0, 10.0): 40, (10.0, 999.0): 30,
}


def _range_score(value: float, ranges: dict) -> int:
    for (lo, hi), score in ranges.items():
        if lo <= value < hi:
            return score
    return 50


# ── Regex patterns ───────────────────────────────────────────────────

_INTERVAL_PATTERNS = {
    "heart_rate_bpm":  re.compile(r"Heart\s+Rate\s+(\d+)\s*bpm", re.I),
    "pr_interval_ms":  re.compile(r"PR\s+Interval\s+(\d+)\s*ms", re.I),
    "qrs_interval_ms": re.compile(r"QRS\s+Interval\s+(\d+)\s*ms", re.I),
    "qt_interval_ms":  re.compile(r"(?<!c\s)QT\s+Interval\s+(\d+)\s*ms", re.I),
    "qtc_interval_ms": re.compile(r"QTc\s+Interval\s+(\d+)\s*ms", re.I),
}
_PATIENT_RE = re.compile(r"^(.+?)\s+(\d+)\s+year\(s\)", re.I | re.M)
_DATE_RE = re.compile(r"Date:\s*(\d{1,2}\s+\w+\s+\d{4})", re.I)
_SDNN_RE = re.compile(r"SDNN\s*:\s*([\d.]+)", re.I)
_RMSSD_RE = re.compile(r"RMSSD\s*:\s*([\d.]+)", re.I)
_NN50_RE = re.compile(r"NN50\s*:\s*([\d.]+)", re.I)
_LF_RE = re.compile(r"LF:\s*([\d.]+)\s*ms", re.I)
_HF_RE = re.compile(r"HF:\s*([\d.]+)\s*ms", re.I)
_LF_HF_RE = re.compile(r"LF/HF\s*:\s*([\d.]+)", re.I)
_STRESS_SENTENCE_RE = re.compile(r"(Low|Moderate|High):\s*(.+?)(?:\n|$)", re.I)
_HRV_ANALYSIS_RE = re.compile(
    r"HRV\s+(?:parameters?\s+in\s+)?(abnormal|normal)\s+range", re.I,
)
_NORMAL_ECG_RE = re.compile(r"Normal\s+ECG", re.I)
_ABNORMAL_ECG_RE = re.compile(r"Abnormal", re.I)


def _clean_doubled_chars(text: str) -> str:
    """Fix PDF extraction doubling: 'SSDDDAANNNN' → 'SDANN', etc."""
    text = re.sub(r"(\d)\1\.\.(\d)\2(\d)\3(\d)\4", r"\1.\2\3\4", text)
    text = re.sub(r"([A-Za-z])\1", r"\1", text)
    text = re.sub(r"(\d)\1(\d)\2", r"\1\2", text)
    text = text.replace("%%", "%")
    return text


def _safe_float(val: str) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _extract_common_fields(text: str, result: EcgResult):
    """Extract patient info and ECG intervals from text."""
    m = _PATIENT_RE.search(text)
    if m:
        raw_name = m.group(1).strip()
        raw_name = re.sub(
            r"^(NAME\s+AGE\s+GENDER\s+HEIGHT\s+WEIGHT\s+REPORT\s+ID\s*\n?\s*)",
            "", raw_name, flags=re.I,
        ).strip()
        result.patient_name = raw_name.title()
        result.patient_age = m.group(2).strip()
    m = _DATE_RE.search(text)
    if m:
        result.scan_date = m.group(1).strip()
    for field_name, pattern in _INTERVAL_PATTERNS.items():
        m = pattern.search(text)
        if m:
            setattr(result, field_name, int(m.group(1)))


def _set_rhythm(text: str, result: EcgResult):
    """Determine rhythm and set score."""
    if _NORMAL_ECG_RE.search(text):
        result.overall_evaluation = "Normal ECG"
        result.rhythm = "Normal"
        result.rhythm_score = 95
    elif _ABNORMAL_ECG_RE.search(text):
        result.overall_evaluation = "Abnormal ECG"
        result.rhythm = "Abnormal"
        result.rhythm_score = 45
    else:
        result.rhythm = "Unknown"
        result.rhythm_score = 50


def _compute_scores(result: EcgResult):
    """Compute clinical scores from raw values."""
    if result.heart_rate_bpm > 0:
        result.hr_score = _range_score(result.heart_rate_bpm, HR_RANGES)
    if result.qtc_interval_ms > 0:
        result.qtc_score = _range_score(result.qtc_interval_ms, QTC_RANGES)
    if result.sdnn_ms > 0:
        result.hrv_score = _range_score(result.sdnn_ms, SDNN_RANGES)
    if result.lf_hf_ratio > 0:
        result.lf_hf_score = _range_score(result.lf_hf_ratio, LF_HF_RANGES)

    scores, weights = [], []
    if result.hr_score > 0:
        scores.append(result.hr_score); weights.append(3)
    if result.qtc_score > 0:
        scores.append(result.qtc_score); weights.append(2)
    if result.rhythm_score > 0:
        scores.append(result.rhythm_score); weights.append(2)
    if result.hrv_score > 0:
        scores.append(result.hrv_score); weights.append(1)
    if result.lf_hf_score > 0:
        scores.append(result.lf_hf_score); weights.append(1)
    if scores:
        tw = sum(weights)
        result.cardiovascular_score = int(
            sum(s * w for s, w in zip(scores, weights)) / tw
        )


def parse_ecg_pdf(pdf_path: str) -> EcgResult:
    """Parse a Spandan ECG PDF and extract cardiac parameters."""
    result = EcgResult()
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages[:1]:
                text += (page.extract_text() or "") + "\n"
    except Exception as e:
        log.error(f"Failed to open ECG PDF: {e}")
        return result

    _extract_common_fields(text, result)
    _set_rhythm(text, result)
    _compute_scores(result)
    log.info(f"ECG parsed: HR={result.heart_rate_bpm}, QTc={result.qtc_interval_ms}")
    return result


def parse_hrv_pdf(pdf_path: str) -> EcgResult:
    """Parse a Spandan HRV PDF and extract HRV + ECG parameters."""
    result = EcgResult()
    all_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                all_text += (page.extract_text() or "") + "\n"
    except Exception as e:
        log.error(f"Failed to open HRV PDF: {e}")
        return result

    cleaned = _clean_doubled_chars(all_text)
    _extract_common_fields(all_text, result)

    # HRV time-domain — search RAW text first (SDNN : 26.98),
    # then cleaned text as fallback (doubled chars like SSDDDAANNNN)
    for regex, attr in [(_SDNN_RE, "sdnn_ms"), (_RMSSD_RE, "rmssd_ms"),
                        (_NN50_RE, "nn50")]:
        m = regex.search(all_text) or regex.search(cleaned)
        if m:
            setattr(result, attr, _safe_float(m.group(1)))

    # HRV frequency-domain — same strategy
    for regex, attr in [(_LF_RE, "lf_power"), (_HF_RE, "hf_power"),
                        (_LF_HF_RE, "lf_hf_ratio")]:
        m = regex.search(all_text) or regex.search(cleaned)
        if m:
            setattr(result, attr, _safe_float(m.group(1)))

    # Stress coping
    m = _STRESS_SENTENCE_RE.search(all_text)
    if m:
        result.stress_coping = m.group(1).strip().title()
        result.stress_analysis = m.group(2).strip()

    # HRV analysis verdict
    m = _HRV_ANALYSIS_RE.search(all_text)
    if m:
        result.hrv_analysis = m.group(1).lower()

    _set_rhythm(all_text, result)
    _compute_scores(result)
    log.info(
        f"HRV parsed: SDNN={result.sdnn_ms}, RMSSD={result.rmssd_ms}, "
        f"LF/HF={result.lf_hf_ratio}, stress={result.stress_coping}"
    )
    return result


def merge_ecg_hrv(ecg: EcgResult, hrv: EcgResult) -> EcgResult:
    """Merge ECG-only and HRV results. ECG wins for intervals, HRV adds HRV data."""
    merged = EcgResult()
    merged.patient_name = hrv.patient_name or ecg.patient_name
    merged.patient_age = hrv.patient_age or ecg.patient_age
    merged.scan_date = hrv.scan_date or ecg.scan_date
    # ECG intervals — prefer dedicated ECG PDF
    merged.heart_rate_bpm = ecg.heart_rate_bpm or hrv.heart_rate_bpm
    merged.pr_interval_ms = ecg.pr_interval_ms or hrv.pr_interval_ms
    merged.qrs_interval_ms = ecg.qrs_interval_ms or hrv.qrs_interval_ms
    merged.qt_interval_ms = ecg.qt_interval_ms or hrv.qt_interval_ms
    merged.qtc_interval_ms = ecg.qtc_interval_ms or hrv.qtc_interval_ms
    merged.rhythm = ecg.rhythm or hrv.rhythm
    merged.overall_evaluation = ecg.overall_evaluation or hrv.overall_evaluation
    # HRV data — only from HRV PDF
    merged.sdnn_ms = hrv.sdnn_ms
    merged.rmssd_ms = hrv.rmssd_ms
    merged.nn50 = hrv.nn50
    merged.lf_power = hrv.lf_power
    merged.hf_power = hrv.hf_power
    merged.lf_hf_ratio = hrv.lf_hf_ratio
    merged.stress_coping = hrv.stress_coping
    merged.stress_analysis = hrv.stress_analysis
    merged.hrv_analysis = hrv.hrv_analysis
    # Recompute scores
    if ecg.rhythm == "Normal":
        merged.rhythm_score = 95
    elif ecg.rhythm == "Abnormal":
        merged.rhythm_score = 45
    else:
        merged.rhythm_score = hrv.rhythm_score
    _compute_scores(merged)
    return merged


def to_deterministic_dict(result: EcgResult) -> dict:
    """Convert parsed ECG+HRV result to a flat deterministic dictionary."""
    return {
        "patient": {
            "name": result.patient_name,
            "age": result.patient_age,
            "date": result.scan_date,
        },
        "ecg": {
            "heart_rate_bpm": result.heart_rate_bpm,
            "pr_interval_ms": result.pr_interval_ms,
            "qrs_interval_ms": result.qrs_interval_ms,
            "qt_interval_ms": result.qt_interval_ms,
            "qtc_interval_ms": result.qtc_interval_ms,
            "rhythm": result.rhythm,
            "overall_evaluation": result.overall_evaluation,
        },
        "hrv": {
            "sdnn_ms": result.sdnn_ms,
            "rmssd_ms": result.rmssd_ms,
            "nn50": result.nn50,
            "lf_power": result.lf_power,
            "hf_power": result.hf_power,
            "lf_hf_ratio": result.lf_hf_ratio,
            "stress_coping": result.stress_coping,
            "stress_analysis": result.stress_analysis,
            "hrv_analysis": result.hrv_analysis,
        },
        "scores": {
            "hr_score": result.hr_score,
            "qtc_score": result.qtc_score,
            "rhythm_score": result.rhythm_score,
            "hrv_score": result.hrv_score,
            "lf_hf_score": result.lf_hf_score,
            "cardiovascular_score": result.cardiovascular_score,
        },
    }
