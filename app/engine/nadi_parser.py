"""Nadi Tarangini PDF parser — extracts Ayurvedic pulse data, no LLM.

Parses OCR text from Nadi Tarangini (Swasthya Darshika) reports to extract:
  - Dosha analysis (Prakriti, Vikruti)
  - Pulse rate, rhythm
  - Health parameters (digestion, stress, immunity, etc.)
  - Organ insights
  - Wellness recommendations (diet, yoga, supplements, medicine)

Same OCR text → same values, always.
"""
import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class HealthParam:
    """Single health parameter from the Nadi report."""
    name: str
    level: str = ""       # "Low" / "Medium" / "High"
    percentage: int = 0   # 0-100
    description: str = ""


@dataclass
class NadiResult:
    """Parsed result from a Nadi Tarangini report."""
    # Patient info
    patient_name: str = ""
    patient_age: str = ""
    scan_date: str = ""
    weight_kg: float = 0.0
    height_cm: float = 0.0

    # Dosha
    prakriti: str = ""        # e.g. "Pitta Kapha"
    vikruti: str = ""         # e.g. "Vata"
    pulse_rate_bpm: int = 0
    rhythm: str = ""          # "Regular" / "Irregular"
    rhythm_remark: str = ""   # "Good" / etc.

    # Health parameters
    health_params: dict = field(default_factory=dict)

    # Organ insights
    organ_insights: dict = field(default_factory=dict)

    # Potential risks
    potential_risks: list = field(default_factory=list)

    # Wellness recommendations
    diet_eat: list = field(default_factory=list)
    diet_avoid: list = field(default_factory=list)
    yoga_poses: list = field(default_factory=list)
    exercises: list = field(default_factory=list)
    panchakarma: list = field(default_factory=list)
    aromatherapy: list = field(default_factory=list)
    supplements: list = field(default_factory=list)
    medicines: list = field(default_factory=list)
    herbs: list = field(default_factory=list)


# ── Health parameter level → score mapping ───────────────────────────
# For "positive" params: High = good → high score
# For "negative" params: High = bad → low score
# For "neutral" params: Medium = okay

POSITIVE_PARAMS = {"hydration"}
NEGATIVE_PARAMS = {"toxin", "stress", "overthinking"}

LEVEL_SCORE_DEFAULT = {"low": 40, "medium": 65, "high": 90}
LEVEL_SCORE_NEGATIVE = {"low": 90, "medium": 65, "high": 40}


def level_to_score(param_name: str, level: str) -> int:
    """Convert a named health parameter level to a numeric score."""
    lvl = level.strip().lower()
    if param_name.lower() in NEGATIVE_PARAMS:
        return LEVEL_SCORE_NEGATIVE.get(lvl, 50)
    return LEVEL_SCORE_DEFAULT.get(lvl, 50)


# ── Regex patterns ───────────────────────────────────────────────────

_PATIENT_NAME_RE = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\(\d+\)\s*Patient\s*Name",
    re.I,
)
# Fallback: look for "Patient Details\nName (ID) Patient Name"
_PATIENT_NAME_FALLBACK_RE = re.compile(
    r"Patient\s+Details\s*\n\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\(",
    re.I,
)
_DATE_RE = re.compile(r"Date\s+(\d{1,2}\s+\w+\s+\d{4})", re.I)
_WEIGHT_RE = re.compile(r"Weight\s*:?\s*([\d.]+)\s*Kg", re.I)
_HEIGHT_RE = re.compile(r"Height\s*:?\s*([\d.]+)\s*Cm", re.I)
_AGE_RE = re.compile(r"(\d+)\s+(Male|Female)", re.I)

_PRAKRITI_RE = re.compile(r"Pra?kr[ui]ti:\s*(.+?)(?:\n|$)", re.I)
_VIKRUTI_RE = re.compile(r"Vikr[ui]ti:\s*(.+?)(?:\n|$)", re.I)

# Pulse rate — two formats seen in OCR:
#   Format 1: "79 Regular" (number first)
#   Format 2: "Irregular Good 81" (rhythm first, number last)
_PULSE_RE = re.compile(r"(\d{2,3})\s+(Regular|Irregular)", re.I)
_PULSE_ALT_RE = re.compile(r"(Regular|Irregular)\s+\w+\s+(\d{2,3})", re.I)
# Fallback: "pulse rate of 81 bpm" in FAQ section
_PULSE_FAQ_RE = re.compile(r"pulse\s+rate\s+of\s+(\d{2,3})\s*bpm", re.I)

# Health parameters: "Digestion Level  Low\n30%"  or  "Toxin Level\nMedium\n40%"
# OCR puts level/% on same or next line, so be flexible with newlines
_HEALTH_PARAM_RE = re.compile(
    r"(Digestion|Toxin|Hydration|Immunity|Flexibility|Overthinking|[Ss]tress)"
    r"\s+Level\s*\n?\s*(Low|Medium|High)\s*\n?\s*(\d{1,3})%",
    re.I,
)
_HEALTH_PARAM_INLINE_RE = re.compile(
    r"(Low|Medium|High)\s+"
    r"(Digestion|Toxin|Hydration|Immunity|Flexibility|Overthinking|[Ss]tress)"
    r"\s+Level\s*\n?\s*(\d{1,3})%",
    re.I,
)

# Organ insights: "Kidney; Your high hydration..."
_ORGAN_RE = re.compile(
    r"(Kidney|Intestine|Bones?|Skin|Muscles?|Liver)[;,]\s*(.+?)(?=\n\s*(?:Kidney|Intestine|Bones?|Skin|Muscles?|Liver)[;,]|\n\s*\d/\d|\Z)",
    re.I | re.S,
)


def parse_nadi_text(ocr_text: str) -> NadiResult:
    """Parse OCR-extracted text from a Nadi Tarangini PDF.

    Args:
        ocr_text: Raw OCR text from all pages of the Nadi PDF.

    Returns:
        NadiResult with all extracted fields.
    """
    result = NadiResult()

    if not ocr_text or not ocr_text.strip():
        log.warning("Empty Nadi text — nothing to parse")
        return result

    # ── Patient info ─────────────────────────────────────────────────
    m = _PATIENT_NAME_FALLBACK_RE.search(ocr_text)
    if not m:
        m = _PATIENT_NAME_RE.search(ocr_text)
    if m:
        result.patient_name = m.group(1).strip().title()

    m = _DATE_RE.search(ocr_text)
    if m:
        result.scan_date = m.group(1).strip()

    m = _WEIGHT_RE.search(ocr_text)
    if m:
        result.weight_kg = _safe_float(m.group(1))

    m = _HEIGHT_RE.search(ocr_text)
    if m:
        result.height_cm = _safe_float(m.group(1))

    m = _AGE_RE.search(ocr_text)
    if m:
        result.patient_age = m.group(1).strip()

    # ── Dosha analysis ───────────────────────────────────────────────
    m = _PRAKRITI_RE.search(ocr_text)
    if m:
        result.prakriti = _clean_dosha(m.group(1))

    m = _VIKRUTI_RE.search(ocr_text)
    if m:
        result.vikruti = _clean_dosha(m.group(1))

    # ── Pulse rate ───────────────────────────────────────────────────
    # Try format 1: "79 Regular"
    m = _PULSE_RE.search(ocr_text)
    if m:
        result.pulse_rate_bpm = int(m.group(1))
        result.rhythm = m.group(2).title()
    else:
        # Try format 2: "Irregular Good 81"
        m = _PULSE_ALT_RE.search(ocr_text)
        if m:
            result.rhythm = m.group(1).title()
            result.pulse_rate_bpm = int(m.group(2))

    # Fallback: "pulse rate of 81 bpm" in FAQ
    if not result.pulse_rate_bpm:
        m = _PULSE_FAQ_RE.search(ocr_text)
        if m:
            result.pulse_rate_bpm = int(m.group(1))

    # Look for "Remark" value near pulse data
    if result.rhythm:
        remark_re = re.compile(
            rf"{result.rhythm}\s+(Good|Fair|Poor|Normal)", re.I
        )
        m = remark_re.search(ocr_text)
        if m:
            result.rhythm_remark = m.group(1).title()

    # ── Health parameters ────────────────────────────────────────────
    for m in _HEALTH_PARAM_RE.finditer(ocr_text):
        name = m.group(1).strip().lower()
        level = m.group(2).strip().title()
        pct = int(m.group(3))
        result.health_params[name] = HealthParam(
            name=name, level=level, percentage=pct,
        )

    for m in _HEALTH_PARAM_INLINE_RE.finditer(ocr_text):
        level = m.group(1).strip().title()
        name = m.group(2).strip().lower()
        pct = int(m.group(3))
        result.health_params[name] = HealthParam(
            name=name, level=level, percentage=pct,
        )

    # ── Organ insights ───────────────────────────────────────────────
    for m in _ORGAN_RE.finditer(ocr_text):
        organ = m.group(1).strip().title()
        insight = m.group(2).strip()
        # Clean OCR artifacts
        insight = re.sub(r"\s+", " ", insight).strip()
        result.organ_insights[organ.lower()] = insight

    # ── Potential risks ──────────────────────────────────────────────
    risk_section = _extract_section(ocr_text, "Potential Risk", "Organ Insights")
    if risk_section:
        # Split on semicolons or sentence boundaries
        risks = re.split(r"[;,]\s*(?=[A-Z])", risk_section)
        result.potential_risks = [r.strip() for r in risks if len(r.strip()) > 10]

    # ── Wellness: Diet ───────────────────────────────────────────────
    diet_section = _extract_section(ocr_text, "Moong Dal|Ghee|Basmati", "Yoga at Home")
    if diet_section:
        _parse_diet(diet_section, result)

    # ── Wellness: Yoga & Exercise ────────────────────────────────────
    yoga_section = _extract_section(ocr_text, "Yoga at Home", "Exercise Outside")
    if yoga_section:
        result.yoga_poses = _extract_items(yoga_section, [
            "Adho Mukha Svanasana", "Surya Namaskar", "Anulom Vilom",
            "Padmasana", "Bhujangasana", "Virabhadrasana", "Pranayama",
            "Shavasana", "Vajrasana", "Trikonasana",
        ])

    exercise_section = _extract_section(ocr_text, "Exercise Outside", "Panchakarma")
    if exercise_section:
        result.exercises = _extract_items(exercise_section, [
            "Walking", "Cycling", "Strength training", "Jogging",
            "Plank", "Squats", "Swimming", "Stretching",
        ])

    # ── Wellness: Panchakarma & Aromatherapy ─────────────────────────
    panch_section = _extract_section(ocr_text, "Panchakarma", "Aromatherapy")
    if panch_section:
        result.panchakarma = _extract_items(panch_section, [
            "Abhyanga", "Shirodhara", "Swedana", "Nasya",
            "Basti", "Virechana", "Vamana",
        ])

    aroma_section = _extract_section(ocr_text, "Aromatherapy", "Ayurvedic")
    if aroma_section:
        result.aromatherapy = _extract_items(aroma_section, [
            "Sandalwood", "Lavender", "Orange", "Eucalyptus",
            "Peppermint", "Rose", "Jasmine", "Frankincense",
        ])

    # ── Wellness: Supplements & Medicine ─────────────────────────────
    supp_section = _extract_section(ocr_text, "Ayurvedic Supplements", "Health supplements")
    health_supp = _extract_section(ocr_text, "Health supplements", "Ayurvedic Herbs")
    if supp_section:
        result.supplements = _extract_items(supp_section, [
            "Ashwagandha", "Amla", "Triphala", "Brahmi", "Shatavari",
        ])
    if health_supp:
        result.supplements.extend(_extract_items(health_supp, [
            "Omega-3", "Multivitamin", "Vitamin D", "Zinc", "Iron",
            "Calcium", "Probiotics", "Magnesium",
        ]))

    herbs_section = _extract_section(ocr_text, "Ayurvedic Herbs", "Ayurvedic Medicines")
    if herbs_section:
        result.herbs = _extract_items(herbs_section, [
            "Ashwagandha", "Amla", "Tulsi", "Turmeric", "Neem",
            "Ginger", "Guduchi", "Haritaki",
        ])

    med_section = _extract_section(ocr_text, "Ayurvedic Medicines", "FAQ")
    if med_section:
        result.medicines = _extract_items(med_section, [
            "Chyawanprash", "Giloy", "Triphala", "Dashamoola",
            "Trikatu", "Sitopaladi", "Mahasudarshan",
        ])

    log.info(
        f"Nadi parsed: pulse={result.pulse_rate_bpm}, "
        f"prakriti={result.prakriti}, vikruti={result.vikruti}, "
        f"params={len(result.health_params)}"
    )
    return result


def _clean_dosha(raw: str) -> str:
    """Clean dosha text: remove 'blend of...' suffix."""
    raw = raw.strip()
    # Remove everything after newline
    raw = raw.split("\n")[0].strip()
    # Remove trailing description
    raw = re.sub(r"\s*blend\s+of\s+.*$", "", raw, flags=re.I)
    return raw.strip()


def _extract_section(text: str, start_pattern: str, end_pattern: str) -> str:
    """Extract text between two section markers."""
    pattern = re.compile(
        rf"({start_pattern})(.*?)(?={end_pattern}|\Z)",
        re.I | re.S,
    )
    m = pattern.search(text)
    if m:
        return m.group(0).strip()
    return ""


def _extract_items(section: str, known_items: list) -> list:
    """Find known items in a section of text."""
    found = []
    for item in known_items:
        if re.search(re.escape(item), section, re.I):
            found.append(item)
    return found


def _parse_diet(section: str, result: NadiResult):
    """Parse diet section into eat/avoid lists."""
    # Items before descriptions that contain positive keywords → eat
    # Items with negative keywords → avoid
    eat_keywords = [
        "Moong Dal", "Ghee", "Basmati Rice", "Steamed Vegetables",
        "Warm Milk", "Roti", "Fresh Ginger", "Khichdi",
        "Oats", "Lentils", "Coconut",
    ]
    avoid_keywords = [
        "Raw Vegetables", "Cold Drinks", "Spicy Foods", "Fried Foods",
        "Canned", "Processed Foods", "Excessive Caffeine", "Bitter Greens",
        "Ice Cream", "Carbonated",
    ]
    result.diet_eat = _extract_items(section, eat_keywords)
    result.diet_avoid = _extract_items(section, avoid_keywords)


def _safe_float(val: str) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def to_deterministic_dict(result: NadiResult) -> dict:
    """Convert parsed Nadi result to a flat deterministic dictionary."""
    # Build health param scores
    param_scores = {}
    for name, param in result.health_params.items():
        param_scores[name] = {
            "level": param.level,
            "percentage": param.percentage,
            "score": level_to_score(name, param.level),
        }

    return {
        "patient": {
            "name": result.patient_name,
            "age": result.patient_age,
            "date": result.scan_date,
            "weight_kg": result.weight_kg,
            "height_cm": result.height_cm,
        },
        "dosha": {
            "prakriti": result.prakriti,
            "vikruti": result.vikruti,
        },
        "pulse": {
            "rate_bpm": result.pulse_rate_bpm,
            "rhythm": result.rhythm,
            "remark": result.rhythm_remark,
        },
        "health_params": param_scores,
        "organ_insights": result.organ_insights,
        "potential_risks": result.potential_risks,
        "wellness": {
            "diet_eat": result.diet_eat,
            "diet_avoid": result.diet_avoid,
            "yoga": result.yoga_poses,
            "exercise": result.exercises,
            "panchakarma": result.panchakarma,
            "aromatherapy": result.aromatherapy,
            "supplements": result.supplements,
            "herbs": result.herbs,
            "medicines": result.medicines,
        },
    }
