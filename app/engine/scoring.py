"""Deterministic scoring engine — uses parsed device data, not LLM guesses.

Bioresonance system scores are computed from actual organ E-level averages.
Dimension scores are computed from metrics + ECG/HRV + Nadi health params.
Same input data → same scores, always.
"""
import logging

log = logging.getLogger(__name__)

# ── Metric-based scoring rubrics ─────────────────────────────────────

BMI_RANGES = {
    (0, 18.5): 55,
    (18.5, 24.9): 90,
    (25.0, 29.9): 65,
    (30.0, 100): 40,
}

BODY_FAT_RANGES = {
    (0, 8): 60,
    (8, 20): 90,
    (20, 30): 70,
    (30, 100): 45,
}

HEART_RATE_RANGES = {
    (0, 50): 60,
    (50, 100): 90,
    (100, 200): 55,
}

QTC_RANGES = {
    (0, 250): 50, (250, 300): 65, (300, 450): 90,
    (450, 500): 55, (500, 999): 35,
}

# Nadi health param level → score
# For "negative" params (stress, toxin, overthinking): High = bad → low score
# For "positive" params (hydration): High = good → high score
# For "neutral" params: Medium = acceptable
NADI_POSITIVE = {"hydration"}
NADI_NEGATIVE = {"toxin", "stress", "overthinking"}
NADI_SCORE_DEFAULT = {"low": 40, "medium": 65, "high": 90}
NADI_SCORE_NEGATIVE = {"low": 90, "medium": 65, "high": 40}


def _nadi_param_score(param_name: str, level: str) -> int:
    """Convert a Nadi health parameter level to a numeric score."""
    lvl = level.strip().lower()
    if param_name.lower() in NADI_NEGATIVE:
        return NADI_SCORE_NEGATIVE.get(lvl, 50)
    return NADI_SCORE_DEFAULT.get(lvl, 50)


# ── BioWell organ-to-system mapping ──────────────────────────────────
# BioWell Page 2 scores use the Functional/energetic table Balance%.
# If Balance% is unavailable, the Energy Joules value is interpreted via
# the BioWell energy rules from summary_requirement.docx.
BIOWELL_ORGAN_SYSTEM_MAP = {
    "nervous": [
        "Nervous system", "Head", "Eyes", "Ears, nose, maxillary sinus",
        "Jaw, Teeth", "Cerebral zone (cortex)", "Cerebral zone (vessels)",
        "Hypothalamus", "Epiphysis", "Pituitary gland",
    ],
    "cardiovascular": [
        "Cardiovascular system", "Heart", "Cerebral zone (vessels)",
        "Coronary vessels",
    ],
    "respiratory": [
        "Respiratory system", "Throat, larynx, trachea", "Trachea",
        "Larynx", "Bronchi", "Thorax zone",
    ],
    "musculoskeletal": ["Musculoskeletal system", "Spine - cervical zone",
                         "Spine - thorax zone", "Spine - lumbar zone", "Sacrum",
                         "Coccyx, Pelvis minor zone"],
    "digestive": ["Digestive system", "Colon - ascending", "Colon - transverse",
                   "Colon - descending", "Colon - sigmoid", "Duodenum", "Ileum",
                   "Jejunum", "Liver", "Pancreas", "Gallbladder", "Appendix",
                   "Abdominal zone", "Rectum", "Blind gut"],
    "integumentary": ["Head"],
    "endocrine": ["Endocrine system", "Thyroid", "Thyroid gland",
                  "Hypothalamus", "Hypophysis", "Pituitary gland",
                  "Epiphysis", "Pancreas", "Adrenals", "Spleen"],
    "urogenital": ["Urogenital system", "Kidneys"],
    "reproductive": ["Urogenital system", "Kidneys", "Prostate"],
    "immune": ["Immune system"],
}

BIOWELL_SYSTEM_GROUP_MAP = {
    "nervous": ["Nervous system"],
    "cardiovascular": ["Cardiovascular system"],
    "respiratory": ["Respiratory system"],
    "musculoskeletal": ["Musculoskeletal system"],
    "digestive": ["Digestive system"],
    "integumentary": ["Head"],
    "endocrine": ["Endocrine system"],
    "urogenital": ["Urogenital system"],
    "reproductive": ["Reproductive system"],
    "immune": ["Immune system"],
}


def _biowell_balance_to_score(balance_percent: float) -> int:
    """Convert BioWell Balance% into a Page 2 system score."""
    return max(1, min(100, int(round(balance_percent))))


def _iter_biowell_organ_rows(organ_energies):
    """Yield BioWell organ rows from old dict or new list extraction shapes."""
    if isinstance(organ_energies, dict):
        for organ_name, entry in organ_energies.items():
            yield organ_name, entry
        return

    if isinstance(organ_energies, list):
        for entry in organ_energies:
            if not isinstance(entry, dict):
                continue
            organ_name = (
                entry.get("organ")
                or entry.get("organ_name")
                or entry.get("name")
                or entry.get("system")
                or ""
            )
            if organ_name:
                yield organ_name, entry


def _biowell_entry_balance(entry) -> float | None:
    """Return Balance% for BioWell score calculation."""
    if isinstance(entry, dict):
        value = (
            entry.get("balance_percent")
            or entry.get("balance")
            or entry.get("balance_pct")
        )
        if value is None:
            # Backward compatibility: old LLM cache put Balance% into this key.
            legacy_value = entry.get("energy level or status")
            if legacy_value is not None and float(legacy_value) > 10:
                value = legacy_value
        return float(value) if value is not None else None

    value = float(entry)
    return value if value > 10 else None


def _biowell_entry_energy(entry) -> float | None:
    """Return Energy Joules x10-2 for summary interpretation only."""
    if not isinstance(entry, dict):
        value = float(entry)
        return value if value <= 10 else None
    value = entry.get("energy_joules") or entry.get("energy")
    return float(value) if value is not None else None


def _biowell_entry_group(entry) -> str:
    """Return the BioWell table system group, if extraction preserved it."""
    if not isinstance(entry, dict):
        return ""
    return (
        entry.get("system_group")
        or entry.get("system")
        or entry.get("group")
        or ""
    )


def _biowell_energy_to_score(energy: float) -> int:
    """Convert BioWell organ energy level (0-10 Joules x10-2) to 0-100 score.

    Normal range: 4.0–7.0 → 70-90
    Low (<4.0): proportionally lower
    Increased (>7.0): moderate concern → 55-70
    Very high (>9.0): high concern → 40-55
    """
    if energy <= 0:
        return 30
    if energy < 3.0:
        return 30 + int((energy / 3.0) * 20)  # 30-50
    if energy < 4.0:
        return 50 + int(((energy - 3.0) / 1.0) * 20)  # 50-70
    if energy <= 7.0:
        return 70 + int(((energy - 4.0) / 3.0) * 20)  # 70-90
    if energy <= 9.0:
        return 70 - int(((energy - 7.0) / 2.0) * 15)  # 70-55
    return max(35, 55 - int(((energy - 9.0) / 3.0) * 20))  # 55-35


def _compute_biowell_system_scores(biowell_data: dict) -> dict:
    """Compute body system scores from BioWell organ energy levels."""
    organ_energies = biowell_data.get("organ_energy_levels", {})
    if not organ_energies:
        return {}

    rows = list(_iter_biowell_organ_rows(organ_energies))
    scores = {}
    for sys_key, organ_names in BIOWELL_ORGAN_SYSTEM_MAP.items():
        energy_values = []
        group_names = set(BIOWELL_SYSTEM_GROUP_MAP.get(sys_key, []))

        # Preferred path for new extraction: use the table's own system group.
        for _, entry in rows:
            if _biowell_entry_group(entry) in group_names:
                try:
                    e = _biowell_entry_balance(entry)
                    if e is not None and e > 0:
                        energy_values.append(e)
                except (ValueError, TypeError):
                    pass

        # Fallback for old cached dict extraction: match by organ name.
        if not energy_values:
            for organ_name, entry in rows:
                if organ_name in organ_names:
                    try:
                        e = _biowell_entry_balance(entry)
                        if e is not None and e > 0:
                            energy_values.append(e)
                    except (ValueError, TypeError):
                        pass

        # Reproductive is not always a first-class BioWell table group.
        # If absent, use prostate/reproductive markers from urogenital rows.
        if not energy_values and sys_key == "reproductive":
            for organ_name, entry in rows:
                if organ_name == "Prostate":
                    try:
                        e = _biowell_entry_balance(entry)
                        if e is not None and e > 0:
                            energy_values.append(e)
                    except (ValueError, TypeError):
                        pass

        if energy_values:
            avg_value = sum(energy_values) / len(energy_values)
            scores[sys_key] = _biowell_balance_to_score(avg_value)

    return scores


def compute_scores(
    report: dict,
    biores_data: dict | None = None,
    ecg_data: dict | None = None,
    nadi_data: dict | None = None,
    biowell_data: dict | None = None,
) -> dict:
    """Apply deterministic scoring rules to a report.

    Args:
        report:       The raw report dict from LLM synthesis.
        biores_data:  Parsed bioresonance dictionary (from bioresonance_parser).
        ecg_data:     Parsed ECG+HRV dictionary (from ecg_parser).
        nadi_data:    Parsed Nadi dictionary (from nadi_parser).
        biowell_data: Parsed BioWell dictionary (from LLM extraction).

    Returns:
        The same report dict with deterministic scores applied.
    """
    metrics = report.get("metrics", {})
    dimensions = report.get("dimensions", {})
    systems = report.get("systems", {})

    # ── System scores: BioWell PRIMARY, Bioresonance FALLBACK ────────
    biowell_scores = {}
    if biowell_data:
        biowell_scores = _compute_biowell_system_scores(biowell_data)
        if biowell_scores:
            log.info(f"Using BioWell-based system scores (primary): {list(biowell_scores.keys())}")

    biores_scores = {}
    if biores_data and "system_scores" in biores_data:
        biores_scores = biores_data["system_scores"]

    for sys_key in [
        "nervous", "cardiovascular", "respiratory", "musculoskeletal",
        "digestive", "integumentary", "endocrine", "urogenital",
        "reproductive", "immune",
    ]:
        # BioWell first, then Bioresonance fallback, then LLM fallback
        score = biowell_scores.get(sys_key)
        if score is None:
            score = biores_scores.get(sys_key)
        if score is None or not isinstance(score, (int, float)) or score <= 0:
            score = systems.get(sys_key, {}).get("score", 50)
        score = max(1, min(100, int(score)))

        if sys_key not in systems:
            systems[sys_key] = {}
        systems[sys_key]["score"] = score
        systems[sys_key]["status"] = _status(score)

    # ── Dimension scores: from all device data ───────────────────────
    physical_score = _score_physical(metrics, ecg_data, nadi_data)
    dimensions.setdefault("physical", {})["score"] = physical_score

    emotional_score = _score_emotional(metrics, systems, nadi_data)
    dimensions.setdefault("emotional", {})["score"] = emotional_score

    psychological_score = _score_psychological(metrics, systems, ecg_data, nadi_data)
    dimensions.setdefault("psychological", {})["score"] = psychological_score

    spiritual_score = _score_spiritual(metrics)
    dimensions.setdefault("spiritual", {})["score"] = spiritual_score

    report["dimensions"] = dimensions
    report["systems"] = systems
    return report


def _score_physical(
    metrics: dict,
    ecg_data: dict | None = None,
    nadi_data: dict | None = None,
) -> int:
    """Physical dimension: BMI + bodyFat + HR + QTc + Nadi digestion/flexibility."""
    scores = []
    bmi = _safe_float(metrics.get("bmi"))
    if bmi and bmi > 0:
        scores.append(_range_score(bmi, BMI_RANGES))
    bf = _safe_float(metrics.get("bodyFat"))
    if bf and bf > 0:
        scores.append(_range_score(bf, BODY_FAT_RANGES))
    hr = _safe_float(metrics.get("heartRate"))
    if hr and hr > 0:
        scores.append(_range_score(hr, HEART_RATE_RANGES))

    # ECG QTc score
    if ecg_data:
        ecg_scores = ecg_data.get("scores", {})
        qtc = ecg_scores.get("qtc_score", 0)
        if qtc > 0:
            scores.append(qtc)

    # Nadi digestion + flexibility
    if nadi_data:
        params = nadi_data.get("health_params", {})
        for p in ["digestion", "flexibility"]:
            param = params.get(p, {})
            if param.get("level"):
                scores.append(_nadi_param_score(p, param["level"]))

    return int(sum(scores) / len(scores)) if scores else 50


def _score_emotional(
    metrics: dict,
    systems: dict,
    nadi_data: dict | None = None,
) -> int:
    """Emotional dimension: energyReserve + nervous system + Nadi stress/overthinking."""
    scores = []
    er = _safe_float(metrics.get("energyReserve"))
    if er and er > 0:
        scores.append(min(90, int(er)))
    nervous = systems.get("nervous", {}).get("score", 50)
    if isinstance(nervous, (int, float)) and nervous > 0:
        scores.append(int(nervous))

    # Nadi stress + overthinking
    if nadi_data:
        params = nadi_data.get("health_params", {})
        for p in ["stress", "overthinking"]:
            param = params.get(p, {})
            if param.get("level"):
                scores.append(_nadi_param_score(p, param["level"]))

    return int(sum(scores) / len(scores)) if scores else 55


def _score_psychological(
    metrics: dict,
    systems: dict,
    ecg_data: dict | None = None,
    nadi_data: dict | None = None,
) -> int:
    """Psychological dimension: LF/HF + nervous + HRV + Nadi stress/overthinking."""
    scores = []
    lf_hf = _safe_float(metrics.get("lfhfRatio"))
    if lf_hf and lf_hf > 0:
        if 0.8 <= lf_hf <= 2.5:
            scores.append(85)
        elif lf_hf < 0.5 or lf_hf > 4.0:
            scores.append(40)
        else:
            scores.append(60)
    nervous = systems.get("nervous", {}).get("score", 50)
    if isinstance(nervous, (int, float)) and nervous > 0:
        scores.append(int(nervous))

    # ECG HRV score
    if ecg_data:
        hrv_score = ecg_data.get("scores", {}).get("hrv_score", 0)
        if hrv_score > 0:
            scores.append(hrv_score)

    # Nadi stress + overthinking
    if nadi_data:
        params = nadi_data.get("health_params", {})
        for p in ["stress", "overthinking"]:
            param = params.get(p, {})
            if param.get("level"):
                scores.append(_nadi_param_score(p, param["level"]))

    return int(sum(scores) / len(scores)) if scores else 60


def _score_spiritual(metrics: dict) -> int:
    """Spiritual dimension: bioEnergy + energyReserve (Bio-Well primary)."""
    scores = []
    be = _safe_float(metrics.get("bioEnergy"))
    if be and be > 0:
        scores.append(min(95, max(30, int(be))))
    er = _safe_float(metrics.get("energyReserve"))
    if er and er > 0:
        scores.append(min(95, int(er)))
    return int(sum(scores) / len(scores)) if scores else 60


def _range_score(value: float, ranges: dict) -> int:
    for (lo, hi), score in ranges.items():
        if lo <= value < hi:
            return score
    return 50


def _status(score: int) -> str:
    return "Normal" if score >= 70 else "Need Attention"


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
