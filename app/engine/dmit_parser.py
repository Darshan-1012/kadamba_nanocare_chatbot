"""Deterministic DMIT (Dermatoglyphics Multiple Intelligence Test) parser.

Extracts brain dominance, multiple intelligences, quotients, personality type,
learning styles, brain lobe scores, TFRC, and SWOT from consistent PDF format.
NO LLM calls — pure regex + text parsing.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class DMITResult:
    """Parsed DMIT report data."""
    patient_name: str = ""
    patient_age: str = ""

    # Brain dominance
    left_brain_pct: float = 0.0
    right_brain_pct: float = 0.0

    # TFRC (Total Fingerprint Ridge Count)
    tfrc_total: int = 0
    ltrc: int = 0
    rtrc: int = 0

    # Multiple intelligences (name → percentage)
    multiple_intelligences: Dict[str, float] = field(default_factory=dict)

    # Brain lobe scores (name → percentage)
    brain_lobes: Dict[str, float] = field(default_factory=dict)

    # Learning styles
    learning_styles: Dict[str, int] = field(default_factory=dict)

    # Personality
    primary_personality: str = ""
    secondary_personality: str = ""

    # Planning capability
    doing_capability_pct: float = 0.0
    planning_capability_pct: float = 0.0

    # SWOT
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)
    threats: List[str] = field(default_factory=list)

    # Neuron distribution
    neuron_distribution: Dict[str, float] = field(default_factory=dict)


def parse_dmit_pdf(pdf_path: str) -> DMITResult:
    """Parse a DMIT PDF and extract structured data.

    Args:
        pdf_path: Path to the DMIT PDF file.

    Returns:
        DMITResult with all extracted fields.
    """
    # pyrefly: ignore [missing-import]
    import pdfplumber

    result = DMITResult()
    full_text = ""

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                full_text += text + "\n--- PAGE BREAK ---\n"
    except Exception as e:
        log.error(f"Failed to read DMIT PDF: {e}")
        return result

    log.info(f"DMIT: extracted {len(full_text)} chars from PDF")

    # Parse each section
    _parse_patient_info(full_text, result)
    _parse_brain_dominance(full_text, result)
    _parse_tfrc(full_text, result)
    _parse_multiple_intelligences(full_text, result)
    _parse_brain_lobes(full_text, result)
    _parse_learning_styles(full_text, result)
    _parse_personality(full_text, result)
    _parse_planning_capability(full_text, result)
    _parse_swot(full_text, result)
    _parse_neuron_distribution(full_text, result)

    log.info(
        f"DMIT parsed: L={result.left_brain_pct}% R={result.right_brain_pct}% "
        f"TFRC={result.tfrc_total} MI={len(result.multiple_intelligences)} "
        f"personality={result.primary_personality}/{result.secondary_personality}"
    )

    return result


# ── Patient info ─────────────────────────────────────────────────────
def _parse_patient_info(text: str, result: DMITResult):
    m = re.search(r"Name:\s*(.+?)(?:\n|$)", text)
    if m:
        result.patient_name = m.group(1).strip()

    m = re.search(r"Age:\s*(\d+)\s*Years", text)
    if m:
        result.patient_age = m.group(1).strip()


# ── Brain dominance ──────────────────────────────────────────────────
def _parse_brain_dominance(text: str, result: DMITResult):
    m = re.search(
        r"Left\s*Brain[:\s]*(\d+\.?\d*)%\s*Right\s*Brain[:\s]*(\d+\.?\d*)%",
        text, re.IGNORECASE,
    )
    if m:
        result.left_brain_pct = float(m.group(1))
        result.right_brain_pct = float(m.group(2))
        log.debug(f"Brain dominance: L={result.left_brain_pct}% R={result.right_brain_pct}%")


# ── TFRC ─────────────────────────────────────────────────────────────
def _parse_tfrc(text: str, result: DMITResult):
    m = re.search(
        r"LTRC[:\s]*(\d+)\s+(\d+)\s+RTRC[:\s]*(\d+)",
        text, re.IGNORECASE,
    )
    if m:
        result.ltrc = int(m.group(1))
        result.tfrc_total = int(m.group(2))
        result.rtrc = int(m.group(3))
        log.debug(f"TFRC: L={result.ltrc} T={result.tfrc_total} R={result.rtrc}")


# ── Multiple Intelligences ──────────────────────────────────────────
def _parse_multiple_intelligences(text: str, result: DMITResult):
    """Parse MI from the overview page (Page 4 format)."""
    # Pattern: "Logical 13.0%" or "Kinesthetical 13.7%"
    mi_patterns = {
        "logical": r"Logical\s+(\d+\.?\d*)%",
        "linguistic": r"Linguistics?\s+(\d+\.?\d*)%",
        "kinesthetic": r"Kinesthetic(?:al)?\s+(\d+\.?\d*)%",
        "visual_spatial": r"Visual[\-\s]*Spatial\s+(\d+\.?\d*)%",
        "intrapersonal": r"Intrapersonal\s+(\d+\.?\d*)%",
        "interpersonal": r"Interpersonal\s+(\d+\.?\d*)%",
        "naturalistic": r"Naturalistic\s+(\d+\.?\d*)%",
        "musical": r"Musical\s+(\d+\.?\d*)%",
    }
    for name, pattern in mi_patterns.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result.multiple_intelligences[name] = float(m.group(1))


# ── Brain lobes ──────────────────────────────────────────────────────
def _parse_brain_lobes(text: str, result: DMITResult):
    """Parse brain lobe percentages from the chart page (Page 9 format).

    The PDF text for this page looks like:
        Pre-Frontal Frontal Parietal Temporal Occipital
    with percentage values on separate lines above the labels:
        24.39%
        20.49%
        20.00% 18.54%
        16.59%
    We use a two-pass approach: first try the label-then-value pattern,
    then fall back to scanning all percentages near the lobe names.
    """
    # Approach 1: Find the lobe chart section, then collect all N.NN% values
    lobe_section = re.search(
        r"Brain\s+Lobes.*?(?:Page\s+\d+|---\s*PAGE\s+BREAK)", text,
        re.IGNORECASE | re.DOTALL,
    )
    if lobe_section:
        section_text = lobe_section.group(0)
        # Extract all percentages in order — they appear before labels
        pct_values = re.findall(r"(\d+\.\d+)%", section_text)
        lobe_names = ["pre_frontal", "frontal", "parietal", "temporal", "occipital"]
        for i, name in enumerate(lobe_names):
            if i < len(pct_values):
                result.brain_lobes[name] = float(pct_values[i])
        if result.brain_lobes:
            return

    # Approach 2: direct label-value matching
    for name, label in [("pre_frontal", "Pre-Frontal"), ("frontal", "Frontal"),
                         ("parietal", "Parietal"), ("temporal", "Temporal"),
                         ("occipital", "Occipital")]:
        # Match "24.39%" near the label
        m = re.search(rf"(\d+\.\d+)%\s*\n?\s*{label}", text, re.IGNORECASE)
        if not m:
            m = re.search(rf"{label}\s*\n?\s*(\d+\.\d+)%", text, re.IGNORECASE)
        if m:
            result.brain_lobes[name] = float(m.group(1))


# ── Learning styles ──────────────────────────────────────────────────
def _parse_learning_styles(text: str, result: DMITResult):
    for style in ["Visual", "Auditory", "Kinesthetic"]:
        m = re.search(rf"{style}\s+(\d+)%", text, re.IGNORECASE)
        if m:
            result.learning_styles[style.lower()] = int(m.group(1))


# ── Personality type ─────────────────────────────────────────────────
def _parse_personality(text: str, result: DMITResult):
    m = re.search(
        r"(?:My\s+)?Primary\s+Personality\s+(?:is:?\s*)(\w+)",
        text, re.IGNORECASE,
    )
    if m:
        result.primary_personality = m.group(1).strip().title()

    m = re.search(
        r"(?:My\s+)?Secondary\s+Personality\s+(?:is:?\s*)(\w+)",
        text, re.IGNORECASE,
    )
    if m:
        result.secondary_personality = m.group(1).strip().title()


# ── Planning capability ─────────────────────────────────────────────
def _parse_planning_capability(text: str, result: DMITResult):
    """Parse planning capability from Page 13 format.

    PDF text looks like:
        Doing Capability Planning Capability
        48.1% 51.9%
    """
    # Try the multi-line format first
    m = re.search(
        r"Doing\s+Capability\s+Planning\s+Capability\s*\n\s*(\d+\.?\d*)%\s+(\d+\.?\d*)%",
        text, re.IGNORECASE,
    )
    if m:
        result.doing_capability_pct = float(m.group(1))
        result.planning_capability_pct = float(m.group(2))
        return

    # Fallback: separate patterns
    m = re.search(r"Doing\s+Capability\s*\n?\s*(\d+\.?\d*)%", text, re.IGNORECASE)
    if m:
        result.doing_capability_pct = float(m.group(1))

    m = re.search(r"Planning\s+Capability\s*\n?\s*(\d+\.?\d*)%", text, re.IGNORECASE)
    if m:
        result.planning_capability_pct = float(m.group(1))


# ── SWOT ─────────────────────────────────────────────────────────────
def _parse_swot(text: str, result: DMITResult):
    """Parse SWOT from the dedicated SWOT page (Page 7 format).

    The PDF renders as a 2-column layout that pdfplumber flattens into
    interleaved lines:
        1>Highly Adjusting Nature      (strength)
        1>Need Role model              (weakness)
        2>Team Oriented                (strength)
        2>Can be exploited             (weakness)
        ...
        STRENGTH   WEAKNESS
        THREATS
        OPPORTUNITY
        1>Caring too much for others   (threat)
        1>Need human capital...        (opportunity)
        ...
    """
    swot_section = re.search(
        r"SWOT\s+Based\s+Personality\s+Analysis(.*?)(?:Page\s+\d+|---\s*PAGE\s+BREAK)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not swot_section:
        return

    swot_text = swot_section.group(1)

    # Collect all numbered items
    all_items = re.findall(r"\d+>\s*(.+)", swot_text)
    # Clean: insert spaces in run-together text
    all_items = [re.sub(r"([a-z])([A-Z])", r"\1 \2", x.strip()) for x in all_items]
    all_items = [x for x in all_items if x]

    if not all_items:
        return

    # Find where the STRENGTH/WEAKNESS label line appears → splits top half from bottom
    label_idx = None
    lines = swot_text.split("\n")
    item_count_before_label = 0
    for line in lines:
        stripped = line.strip().upper()
        if "STRENGTH" in stripped and "WEAKNESS" in stripped:
            label_idx = item_count_before_label
            break
        if re.match(r"\d+>", line.strip()):
            item_count_before_label += 1

    # Find where THREATS/OPPORTUNITY label appears
    threats_start = None
    item_count = 0
    found_strength_label = False
    for line in lines:
        stripped = line.strip().upper()
        if "STRENGTH" in stripped:
            found_strength_label = True
            continue
        if found_strength_label and ("THREAT" in stripped or "OPPORTUN" in stripped):
            threats_start = item_count
            break
        if re.match(r"\d+>", line.strip()):
            item_count += 1

    # Split items into top group (strengths+weaknesses) and bottom (threats+opportunities)
    if label_idx is not None and threats_start is not None:
        top_items = all_items[:label_idx]
        bottom_items = all_items[label_idx:]
    elif threats_start is not None:
        top_items = all_items[:threats_start]
        bottom_items = all_items[threats_start:]
    else:
        # Best guess: first half is S/W, second half is T/O
        half = len(all_items) // 2
        top_items = all_items[:half]
        bottom_items = all_items[half:]

    # Top group: interleaved (strength, weakness, strength, weakness, ...)
    strengths = []
    weaknesses = []
    for i, item in enumerate(top_items):
        if i % 2 == 0:
            strengths.append(item)
        else:
            weaknesses.append(item)

    # Bottom group: interleaved (threat, opportunity, threat, opportunity, ...)
    threats = []
    opportunities = []
    for i, item in enumerate(bottom_items):
        if i % 2 == 0:
            threats.append(item)
        else:
            opportunities.append(item)

    result.strengths = strengths
    result.weaknesses = weaknesses
    result.opportunities = opportunities
    result.threats = threats

    log.debug(
        f"SWOT: S={len(result.strengths)} W={len(result.weaknesses)} "
        f"O={len(result.opportunities)} T={len(result.threats)}"
    )


# ── Neuron distribution ──────────────────────────────────────────────
def _parse_neuron_distribution(text: str, result: DMITResult):
    """Parse neuron distribution percentages from attributes page."""
    patterns = {
        "picture_smart": r"Picture\s*Smart\s+(\d+\.?\d*)%",
        "people_smart": r"People\s*Smart\s+(\d+\.?\d*)%",
        "emotion_smart": r"Emotion\s*Smart\s+(\d+\.?\d*)%",
        "word_smart": r"Word\s*Smart\s+(\d+\.?\d*)%",
        "self_smart": r"Self\s*Smart\s+(\d+\.?\d*)%",
        "number_smart": r"Number\s*Smart\s+(\d+\.?\d*)%",
        "nature_smart": r"Nature\s*Smart\s+(\d+\.?\d*)%",
        "space_smart": r"Space\s*Smart\s+(\d+\.?\d*)%",
        "fine_motors_smart": r"FineMotors?\s*Smart\s+(\d+\.?\d*)%",
        "gross_motors_smart": r"GrossMotors?\s*Smart\s+(\d+\.?\d*)%",
    }
    for name, pattern in patterns.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result.neuron_distribution[name] = float(m.group(1))


def to_deterministic_dict(result: DMITResult) -> dict:
    """Convert DMITResult to a plain dictionary for JSON serialization."""
    return {
        "patient": {
            "name": result.patient_name,
            "age": result.patient_age,
        },
        "brain_dominance": {
            "left_pct": result.left_brain_pct,
            "right_pct": result.right_brain_pct,
        },
        "tfrc": {
            "total": result.tfrc_total,
            "ltrc": result.ltrc,
            "rtrc": result.rtrc,
        },
        "multiple_intelligences": result.multiple_intelligences,
        "brain_lobes": result.brain_lobes,
        "learning_styles": result.learning_styles,
        "personality": {
            "primary": result.primary_personality,
            "secondary": result.secondary_personality,
        },
        "planning": {
            "doing_pct": result.doing_capability_pct,
            "planning_pct": result.planning_capability_pct,
        },
        "swot": {
            "strengths": result.strengths,
            "weaknesses": result.weaknesses,
            "opportunities": result.opportunities,
            "threats": result.threats,
        },
        "neuron_distribution": result.neuron_distribution,
    }
