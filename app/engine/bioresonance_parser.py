"""Bioresonance PDF parser — extracts organ readings directly, no LLM.

Parses the structured table from Bioresonance PDFs to extract:
  - Organ/tissue name
  - KOD-t (deviation coefficient)
  - E-level (energy percentage)
  - Shape (waveform quality 1-6)

Then maps each organ to a body system and computes per-system scores.
Same PDF → same scores, always.
"""
import logging
import re
from dataclasses import dataclass, field

# pyrefly: ignore [missing-import]
import pdfplumber

log = logging.getLogger(__name__)


@dataclass
class OrganReading:
    """Single organ/tissue reading from the Bioresonance device."""
    name: str
    kod_t: float
    e_level: int       # percentage 0-100
    shape: int         # 1-6 (lower = better)


@dataclass
class BioresonanceResult:
    """Parsed result from a Bioresonance PDF."""
    patient_name: str = ""
    patient_age: str = ""
    scan_date: str = ""
    readings: list = field(default_factory=list)
    system_scores: dict = field(default_factory=dict)
    hormone_levels: dict = field(default_factory=dict)


# ── Organ → Body System keyword mapping ──────────────────────────────

SYSTEM_KEYWORDS = {
    "nervous": [
        "NERVE", "CEREBR", "BRAIN", "SPINAL", "NEURON", "HYPOTHALAMUS",
        "HYPOPHYSIS", "HYPOPHISIS", "EPIPHYSIS", "NEUROHYPOPHISIS",
        "NEUROHYPOPHYSIS", "ENCEPHALON", "MYELENCEPHALON", "PITUITARY",
        "VEGETATIVE NERVOUS", "CRANIAL NERVE", "NEURO",
    ],
    "cardiovascular": [
        "HEART", "ARTERY", "ARTERIA", "ARTERIOL", "VEIN", "AORTA",
        "VESSEL", "CARDIAC", "CORONARY", "VALVE",
    ],
    "respiratory": [
        "LUNG", "PULMONARY", "BRONCH", "TRACHEA", "LARYNX", "NASAL",
        "SINUS", "PHARYNGEAL", "ALVEO",
    ],
    "digestive": [
        "STOMACH", "INTESTIN", "LIVER", "HEPAT", "PANCREA", "GALL",
        "DUODEN", "COLON", "RECTUM", "ESOPHAG", "GULLET", "APPENDIX",
        "GASTRIC", "PYLORIC", "BILE", "MIDRIFF",
    ],
    "musculoskeletal": [
        "BONE", "JOINT", "VERTEBR", "RACHIS", "FEMUR", "SHIN",
        "TENDON", "SKELETON", "MUSCLE", "MYOCYTE",
    ],
    "endocrine": [
        "THYROID", "ADRENAL", "EPINEPHROS", "THYMUS", "PARATHYROID",
        "ISLETS OF LANGERHAN", "ENDOCRINE PART", "PINEALOCYTE",
    ],
    "integumentary": [
        "SKIN", "HAIR", "EYEBALL", "EYE", "EAR ", "TONGUE",
    ],
    "urogenital": [
        "KIDNEY", "NEPHRON", "URETER", "BLADDER", "URINARY",
    ],
    "reproductive": [
        "TESTICLE", "SPERMATOZOON", "OVARY", "UTERUS", "UTERINE",
        "SEMINAL", "MAMMARY", "BREAST", "CERVIX",
    ],
    "immune": [
        "LYMPH", "TONSIL", "SPLEEN", "BLOOD CELL", "BONE MARROW",
        "LEUKOCYTE", "EOSINOPHIL", "NEUTROPHIL", "MONOCYTE",
        "LYMPHOCYTE", "THROMBOCYTE", "RETICULOCYTE", "PLASMOCYTE",
    ],
}

# Hormones to extract separately
HORMONE_NAMES = [
    "CHOLESTERIN", "CORTISOL", "INSULIN", "GLYCOGEN", "ALDOSTERONUM",
    "HEPARINUM", "TESTOSTERONE", "HISTAMINE", "SEROTONIN",
    "NORADRENALINUM", "ADRENALIN", "DNA",
]

# Regex to match a reading line:
# E-level pattern: "XX %" where XX is 1-3 digits
# Shape pattern: single digit 1-6
# KOD-t: a float like 0.232 or 1.775 or 2.131
_READING_RE = re.compile(
    r"(?P<e_level>\d{1,3})\s*%\s*(?P<shape>[1-6])\s*$"
)
_KOD_RE = re.compile(
    r"(?P<kod>\d\.\d{1,4})"
)


def parse_bioresonance_pdf(pdf_path: str) -> BioresonanceResult:
    """Parse a Bioresonance PDF and extract all organ readings.

    Args:
        pdf_path: Path to the Bioresonance PDF file.

    Returns:
        BioresonanceResult with all readings and computed system scores.
    """
    result = BioresonanceResult()
    all_text_lines = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                all_text_lines.extend(text.split("\n"))
    except Exception as e:
        log.error(f"Failed to open Bioresonance PDF: {e}")
        return result

    # ── Extract patient info from first line ─────────────────────────
    if all_text_lines:
        first_line = all_text_lines[0].strip()
        # Pattern: "chandra achyutha 21 YEAR, 24 April 2004"
        patient_match = re.match(
            r"^(.+?)\s+(\d+)\s*YEAR.*?(\d{1,2}[-\s]\w+[-\s]\d{4})?",
            first_line, re.IGNORECASE,
        )
        if patient_match:
            result.patient_name = patient_match.group(1).strip().title()
            result.patient_age = patient_match.group(2).strip()
            if patient_match.group(3):
                result.scan_date = patient_match.group(3).strip()

    # ── Parse organ readings ─────────────────────────────────────────
    # The table has: DATE TIME NAME KOD_t E-level Shape
    # But the text extraction can split across lines, so we aggregate
    current_name_parts = []
    current_kod = None
    
    for line in all_text_lines:
        line = line.strip()
        if not line or line.startswith("DATE") or line == "<Filter is Empty>":
            continue

        # Check if this line has E-level and Shape at the end
        e_match = _READING_RE.search(line)
        
        # Check for KOD-t value (doubled characters like 11..224488 or normal 1.775)
        # Clean doubled chars first
        cleaned_line = _clean_doubled_chars(line)
        kod_match = _KOD_RE.search(cleaned_line)
        
        if e_match:
            e_level = int(e_match.group("e_level"))
            shape = int(e_match.group("shape"))
            
            # Extract name: everything between the time and the KOD-t value
            name = _extract_name(cleaned_line, current_name_parts)
            
            # Get KOD-t
            kod_t = float(kod_match.group("kod")) if kod_match else 0.0
            
            if name and e_level > 0:
                reading = OrganReading(
                    name=name.upper().strip(),
                    kod_t=kod_t,
                    e_level=e_level,
                    shape=shape,
                )
                result.readings.append(reading)
            
            current_name_parts = []
            current_kod = None
        else:
            # This might be a continuation of a multi-line name
            # Remove date/time prefix if present
            name_part = re.sub(
                r"^\d{1,2}-\w{3}-\d{2}\s+\d{2}:\d{2}\s*", "", line
            ).strip()
            if name_part and not name_part.startswith("DATE"):
                current_name_parts.append(name_part)

    log.info(f"Parsed {len(result.readings)} organ readings")

    # ── Extract hormone levels ───────────────────────────────────────
    for reading in result.readings:
        for hormone in HORMONE_NAMES:
            if hormone in reading.name:
                result.hormone_levels[hormone.lower()] = {
                    "e_level": reading.e_level,
                    "shape": reading.shape,
                    "kod_t": reading.kod_t,
                }
                break

    # ── Compute system scores ────────────────────────────────────────
    result.system_scores = _compute_system_scores(result.readings)

    return result


def _clean_doubled_chars(text: str) -> str:
    """Fix PDF extraction doubling: '11..224488' → '1.248', '5544 %%' → '54 %'."""
    # Fix doubled decimals like 11..224488 → 1.2488
    text = re.sub(r"(\d)\1\.\.(\d)\2(\d)\3(\d)\4", r"\1.\2\3\4", text)
    # Fix simpler doubles like 6644 → 64
    text = re.sub(r"(\d)\1(\d)\2", r"\1\2", text)
    # Fix %% → %
    text = text.replace("%%", "%")
    return text


def _extract_name(line: str, name_parts: list) -> str:
    """Extract organ name from a reading line."""
    # Remove date/time prefix
    line = re.sub(r"^\d{1,2}-\w{3}-\d{2}\s+\d{2}:\d{2}\s*", "", line)
    # Remove KOD-t, E-level, Shape from end
    line = re.sub(r"\d+\.\d+\s+\d+\s*%\s*\d\s*$", "", line)
    # Remove just E-level Shape from end  
    line = re.sub(r"\d+\s*%\s*\d\s*$", "", line)
    
    name = line.strip()
    
    # Prepend any multi-line name parts
    if name_parts:
        full_name = " ".join(name_parts)
        if name:
            full_name += " " + name
        return full_name.strip()
    
    return name


def _compute_system_scores(readings: list) -> dict:
    """Map organs to body systems and average their E-levels.

    Same readings → same mapping → same averages → deterministic scores.
    """
    system_readings = {sys: [] for sys in SYSTEM_KEYWORDS}
    unmatched = []

    for reading in readings:
        matched = False
        name_upper = reading.name.upper()
        
        for system, keywords in SYSTEM_KEYWORDS.items():
            for keyword in keywords:
                if keyword in name_upper:
                    system_readings[system].append(reading)
                    matched = True
                    break
            if matched:
                break
        
        if not matched:
            unmatched.append(reading.name)

    scores = {}
    for system, sys_readings in system_readings.items():
        if sys_readings:
            avg_e = sum(r.e_level for r in sys_readings) / len(sys_readings)
            avg_shape = sum(r.shape for r in sys_readings) / len(sys_readings)
            scores[system] = {
                "score": int(round(avg_e)),
                "avg_shape": round(avg_shape, 1),
                "organ_count": len(sys_readings),
                "status": "Normal" if avg_e >= 70 else "Need Attention",
            }
        else:
            scores[system] = {
                "score": 50,
                "avg_shape": 0,
                "organ_count": 0,
                "status": "No Data",
            }

    if unmatched:
        log.debug(f"Unmatched organs: {unmatched[:10]}...")

    return scores


def to_deterministic_dict(result: BioresonanceResult) -> dict:
    """Convert parsed result to a flat deterministic dictionary.

    This dictionary is passed to the LLM as FIXED context so it
    cannot hallucinate different values.
    """
    return {
        "patient": {
            "name": result.patient_name,
            "age": result.patient_age,
            "date": result.scan_date,
        },
        "system_scores": {
            sys: data["score"]
            for sys, data in result.system_scores.items()
        },
        "system_details": result.system_scores,
        "hormone_levels": result.hormone_levels,
        "total_organs_scanned": len(result.readings),
        "summary": {
            "avg_e_level": (
                int(sum(r.e_level for r in result.readings) / len(result.readings))
                if result.readings else 0
            ),
            "organs_needing_attention": [
                r.name for r in result.readings if r.shape >= 5
            ],
            "organs_excellent": [
                r.name for r in result.readings if r.shape <= 2
            ],
        },
    }
