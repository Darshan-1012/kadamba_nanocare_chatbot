"""Deterministic clinical interpretation rules engine.

All rules are sourced from summary_requirement.docx (doctor-verified).
NO LLM calls — pure lookup tables and threshold comparisons.
"""

from __future__ import annotations

import re


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  NADI TARANGINI — Tables 1 & 2                                     ║
# ╚══════════════════════════════════════════════════════════════════════╝

_NADI_PHYSICAL = {
    "digestion": {
        "high": "Excess of pitta (teeksnagni), hyper metabolism",
        "medium": "Moderate digestive capacity",
        "low": "Mandagni (low digestive capacity), poor nutrient absorption, bloating",
    },
    "toxin": {
        "high": "High accumulation of metabolic toxin, manda agni, systemic toxicity",
        "medium": "Moderate toxin levels",
        "low": "Efficient metabolism",
    },
    "hydration": {
        "high": "Electrolyte balance, removal of ama (toxins), balanced agni and kapha",
        "medium": "Moderate hydration levels",
        "low": "Cellular dehydration, toxin accumulation",
    },
    "immunity": {
        "high": "Strong cellular resilience, strong agni and optimal ojas, positive psychological resilience",
        "medium": "Moderate immune function",
        "low": "Tissue exhaustion, mental fatigue, depletion in ojas",
    },
    "flexibility": {
        "high": "Optimal lubricated joints",
        "medium": "Moderate joint flexibility",
        "low": "Less lubrication, restricted range of motion",
    },
}

_NADI_PSYCHOLOGICAL = {
    "overthinking": {
        "high": "Hyperactive nervous system, anxiety",
        "medium": "Moderate mental activity",
        "low": "Calm mental state",
    },
    "stress": {
        "high": "Locked in sympathetic state, physical stress, mental anxiety",
        "medium": "Moderate stress levels",
        "low": "Calm, clear mind, emotional stability",
    },
}


def _classify_nadi_level(pct: float) -> str:
    """Classify a Nadi percentage into high/medium/low."""
    if pct >= 80:
        return "high"
    elif pct >= 40:
        return "medium"
    else:
        return "low"


def interpret_nadi_param(param_name: str, pct: float) -> dict:
    """Interpret a single Nadi Tarangini parameter.

    Args:
        param_name: One of digestion, toxin, hydration, immunity,
                    flexibility, overthinking, stress
        pct: Percentage value (0-100)

    Returns:
        {level, interpretation}
    """
    param_name = param_name.lower().strip()
    lookup = _NADI_PHYSICAL.get(param_name) or _NADI_PSYCHOLOGICAL.get(param_name)
    if not lookup:
        return {"level": "unknown", "interpretation": f"No rule for '{param_name}'"}

    level = _classify_nadi_level(pct)
    return {"level": level, "interpretation": lookup[level]}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  BIOWELL — Tables 3 & 4                                            ║
# ╚══════════════════════════════════════════════════════════════════════╝

_BIOWELL_ENERGY_RANGES = [
    # (min, max, status, risk, interpretation)
    (0,  2,  "Very low energy",   "Mild to moderate risk",
     "Dysfunction of inner organs and systems, malfunction of vegetative balance, metabolic disturbance"),
    (2,  4,  "Low energy",        "Mild to moderate risk",
     "Tiredness, irritability, decreasing of adaptation, hard to compensate disease, deficiency of energy"),
    (4,  6,  "Optimal energy",    "Normal",
     "Optimal adaptation, balanced power inputs and energy consumption"),
    (6,  8,  "Increased energy",  "Low risk to mild risk",
     "Physiological tension, reflected high load on the system, over reaction, activation of systems and organs"),
    (8,  10, "Heightened energy",  "Low risk to mild risk",
     "Significant tension/stress of adaptation and energy-supply systems, hyper reaction with possible derangement of adaptation, presence of inflammatory processes"),
]

_BIOWELL_STRESS_RANGES = [
    # (min, max, level, interpretation)
    (0,    1.5, "Optimal", "Optimal balance between sympathetic/parasympathetic nervous systems"),
    (1.5,  2.3, "Medium",  "Temporary adaptation of the organism to internal or external processes"),
    (2.3,  999, "High",    "Adaptation to some extreme conditions, or internal problems"),
]


def interpret_biowell_energy(joules: float) -> dict:
    """Interpret BioWell energy level (in Joules ×10⁻²).

    Returns:
        {status, risk, interpretation}
    """
    for min_v, max_v, status, risk, interp in _BIOWELL_ENERGY_RANGES:
        if min_v <= joules < max_v:
            return {"status": status, "risk": risk, "interpretation": interp}
    # Fallback for values >= 10
    return {"status": "Heightened energy", "risk": "Low risk to mild risk",
            "interpretation": "Significant tension in energy-supply systems"}


def interpret_biowell_stress(value: float) -> dict:
    """Interpret BioWell stress index (×10⁻²).

    Returns:
        {level, interpretation}
    """
    for min_v, max_v, level, interp in _BIOWELL_STRESS_RANGES:
        if min_v <= value < max_v:
            return {"level": level, "interpretation": interp}
    return {"level": "High", "interpretation": "Extreme conditions or internal problems"}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  CHAKRA ALIGNMENT — Table 5                                        ║
# ╚══════════════════════════════════════════════════════════════════════╝

_CHAKRA_DESCRIPTIONS = {
    "muladara":   "Self-confidence, sexual power",
    "swadistana": "Material work, job or home",
    "manipura":   "Willingness to solve problems",
    "anahatha":   "Love, sympathy, empathy",
    "vishudda":   "Non-material work",
    "agna":       "Approach to solving tasks and search of information",
    "sahasrara":  "Relations with God, fanatic or atheist",
}


def interpret_chakra(pct: float) -> dict:
    """Interpret a chakra alignment percentage.

    Returns:
        {status}
    """
    if pct >= 80:
        return {"status": "Normal"}
    elif pct >= 60:
        return {"status": "Mild deviation"}
    elif pct >= 30:
        return {"status": "Moderate deviation"}
    else:
        return {"status": "Extreme"}


def get_chakra_description(name: str) -> str:
    """Get the fixed description for a chakra by name."""
    return _CHAKRA_DESCRIPTIONS.get(name.lower().strip(), "")


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  ECG PARAMETERS — Table 6                                          ║
# ╚══════════════════════════════════════════════════════════════════════╝

_ECG_PARAMS = {
    "pr_interval": {
        "unit": "ms", "min": 100, "max": 200,
        "hypo": "During exercise, adrenaline surge",
        "hyper": "Hyperkalaemia, AV-nodal blocking (aging tissue, conductive system fibrosis), MI, vagal surge",
    },
    "qrs_interval": {
        "unit": "ms", "min": 60, "max": 120,
        "hypo": "Common in athletes, adult",
        "hyper": "Bundle Branch Blocks (BBB), hyperkalaemia, severe tricyclic antidepressant overdose, VT, LVH",
    },
    "qt_interval": {
        "unit": "ms", "min": 300, "max": 450,
        "hypo": "Adrenaline surge, hypercalcemia, hyperkalaemia, digitalis toxicity",
        "hyper": "Electrolyte deficiencies (hypokalaemia, hypomagnesemia, hypocalcaemia), structural heart disease",
    },
    "qtc_interval": {
        "unit": "ms", "min": 300, "max": 450,
        "hypo": "Hypercalcemia, hyperthermia, SNS impairment",
        "hyper": "Mild alcohol consumption, ALD, ANS impairment",
    },
    "heart_rate": {
        "unit": "bpm", "min": 60, "max": 100,
        "hypo": "Bradycardia — sinus node dysfunction, hypothyroidism, hypothermia, ADE, allergies",
        "hyper": "Tachycardia — physiological due to exercise, stress, fever, dehydration, or pain; caffeine, nicotine, adrenaline surge; hyperthyroidism, anaemia, SVT, VT",
    },
}


def interpret_ecg_param(param: str, value: float) -> dict:
    """Interpret an ECG parameter against its normal range.

    Args:
        param: One of pr_interval, qrs_interval, qt_interval,
               qtc_interval, heart_rate
        value: Observed numeric value

    Returns:
        {status, interpretation, normal_range}
    """
    param = param.lower().strip().replace(" ", "_")
    info = _ECG_PARAMS.get(param)
    if not info:
        return {"status": "unknown", "interpretation": f"No rule for '{param}'",
                "normal_range": ""}

    normal_range = f"{info['min']}-{info['max']} {info['unit']}"
    if value < info["min"]:
        return {"status": "Below normal", "interpretation": info["hypo"],
                "normal_range": normal_range}
    elif value > info["max"]:
        return {"status": "Above normal", "interpretation": info["hyper"],
                "normal_range": normal_range}
    else:
        return {"status": "Normal", "interpretation": "Within normal range",
                "normal_range": normal_range}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  INBODY PARAMETERS — Table 7                                       ║
# ╚══════════════════════════════════════════════════════════════════════╝

def interpret_inbody_visceral_fat(level: float) -> dict:
    """Interpret InBody visceral fat level."""
    if level <= 9:
        return {"status": "Healthy / Normal",
                "interpretation": "Low metabolic risk"}
    elif level <= 14:
        return {"status": "Elevated / Early Warning",
                "interpretation": "Borderline cardiovascular risk"}
    elif level <= 19:
        return {"status": "High Risk",
                "interpretation": "High metabolic risk. Strongly linked with hidden insulin resistance, systemic inflammation, and fatty liver disease"}
    else:
        return {"status": "Very High Risk",
                "interpretation": "Severe risk. Immediate lifestyle or medical clinical intervention is highly advised"}


def interpret_inbody_skeletal_muscle(kg: float) -> dict:
    """Interpret InBody skeletal muscle mass (kg)."""
    if kg < 31.5:
        return {"status": "Hypo-muscular",
                "interpretation": "Insufficient metabolic muscle tissue. Linked to a slower metabolic rate and higher susceptibility to visceral fat storage"}
    elif kg <= 38.5:
        return {"status": "Normo-muscular",
                "interpretation": "Adequate muscle volume to support regular daily tasks, mobility, and structural skeletal protection"}
    else:
        return {"status": "Hyper-muscular",
                "interpretation": "Exceptional amount of active muscle. Considerably boosts baseline caloric burn and insulin sensitivity"}


def interpret_inbody_body_fat(kg: float) -> dict:
    """Interpret InBody body fat mass (kg)."""
    if kg < 10.5:
        return {"status": "Low",
                "interpretation": "Fat below standard physiological requirements. Can impact hormone production and energy levels"}
    elif kg <= 16.8:
        return {"status": "Healthy / Balanced",
                "interpretation": "Provides optimal organ insulation, energy storage, and metabolic function"}
    else:
        return {"status": "High Fat",
                "interpretation": "Associated with increased systemic inflammation, joint stress, and metabolic strain"}


def interpret_inbody_bmi(bmi: float) -> dict:
    """Interpret InBody BMI (kg/m²)."""
    if bmi < 18.5:
        return {"status": "Underweight",
                "interpretation": "May indicate a risk for malnutrition, compromised immune function, or other health issues"}
    elif bmi < 25.0:
        return {"status": "Healthy Weight",
                "interpretation": "Generally associated with optimal health outcomes and a lower risk of chronic diseases"}
    elif bmi < 30.0:
        return {"status": "Overweight",
                "interpretation": "May indicate an increased risk for conditions like high blood pressure, diabetes, and heart disease"}
    else:
        return {"status": "Obesity",
                "interpretation": "Indicates a significantly higher risk for serious health conditions including sleep apnea, joint pain, and cardiovascular disease"}


def interpret_inbody_param(param: str, value: float) -> dict:
    """Dispatch to the correct InBody parameter interpreter."""
    param = param.lower().strip().replace(" ", "_")
    dispatch = {
        "visceral_fat": interpret_inbody_visceral_fat,
        "skeletal_muscle_mass": interpret_inbody_skeletal_muscle,
        "skeletal_muscle": interpret_inbody_skeletal_muscle,
        "body_fat_mass": interpret_inbody_body_fat,
        "body_fat": interpret_inbody_body_fat,
        "bmi": interpret_inbody_bmi,
    }
    fn = dispatch.get(param)
    if fn:
        return fn(value)
    return {"status": "unknown", "interpretation": f"No rule for '{param}'"}


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  BIORESONANCE ENERGY — Table 8                                     ║
# ╚══════════════════════════════════════════════════════════════════════╝

_BIORES_ENERGY_RANGES = [
    # (min_pct, max_pct, level, functional_status, interpretation)
    (90, 101, 1, "Optimal baseline",
     "Optimal: Perfect cellular reserve capacity. Highest level of tissue adaptability"),
    (75, 90,  2, "Healthy Balanced",
     "Healthy: Active functioning. Tissue adapts smoothly to environmental inputs"),
    (60, 75,  3, "Normal",
     "Adequate: But the cells are actively processing a mild metabolic or lifestyle load"),
    (40, 60,  4, "Hyper-Function",
     "Acute Stress: Cellular irritation or functional overload. The system is working overtime to compensate for a stressor"),
    (20, 40,  5, "Hypo-Function",
     "Energetic Depletion: Severe tissue exhaustion. Cell regeneration is slowing down; tissue is losing its self-regulating power"),
    (0,  20,  6, "Decompensation",
     "Cellular Exhaustion: Deep energetic blockages or cellular fatigue. The tissue has exhausted its adaptive energy reserves"),
]


def interpret_biores_energy(pct: float) -> dict:
    """Interpret Bioresonance energy level percentage.

    Returns:
        {level, functional_status, interpretation}
    """
    for min_p, max_p, level, func_status, interp in _BIORES_ENERGY_RANGES:
        if min_p <= pct < max_p:
            return {"level": level, "functional_status": func_status,
                    "interpretation": interp}
    # Fallback
    if pct >= 100:
        return {"level": 1, "functional_status": "Optimal baseline",
                "interpretation": "Perfect cellular reserve capacity"}
    return {"level": 6, "functional_status": "Decompensation",
            "interpretation": "Cellular exhaustion"}




# ======================================================================
#  COMPOSITE: build_interpretations
# ======================================================================

def _status_for_system_score(score: float) -> str:
    """Convert a body-system score (0-100) to a display status string."""
    if score >= 80:
        return "Normal"
    elif score >= 60:
        return "Need attention"
    elif score >= 40:
        return "Moderate concern"
    else:
        return "Needs intervention"


def _level_to_pct(level: str) -> float:
    """Convert a text level (high/medium/low) to a representative percentage."""
    mapping = {"high": 85.0, "medium": 60.0, "low": 25.0}
    return mapping.get(level.strip().lower(), 50.0)


def build_interpretations(
    report: dict,
    biores_data: dict | None = None,
    ecg_data: dict | None = None,
    nadi_data: dict | None = None,
    biowell_data: dict | None = None,
) -> dict:
    """Inject deterministic interpretations into the report dict.

    This is the master function called after synthesis to add all
    doctor-verified interpretations to the report before rendering.
    Mutates report in place and returns it.

    Args:
        report:      The scored report dict (after compute_scores).
        biores_data: Parsed Bioresonance data (from bioresonance_parser).
        ecg_data:    Parsed ECG+HRV data (from ecg_parser).
        nadi_data:   Parsed Nadi data (from nadi_parser).
        biowell_data: Parsed BioWell data.
    """
    metrics = report.get("metrics", {})
    systems = report.get("systems", {})
    dimensions = report.get("dimensions", {})
    interps = report.setdefault("interpretations", {})

    # -- ECG interpretations (Table 6) --
    hr = metrics.get("heartRate")
    if hr is not None:
        interps["heartRate"] = interpret_ecg_param("heart_rate", float(hr))

    if ecg_data:
        ecg_vals = ecg_data.get("ecg", {})
        for param_key, metric_key in [
            ("pr_interval_ms", "pr_interval"),
            ("qrs_interval_ms", "qrs_interval"),
            ("qt_interval_ms", "qt_interval"),
            ("qtc_interval_ms", "qtc_interval"),
        ]:
            val = ecg_vals.get(param_key)
            if val is not None and float(val) > 0:
                interps[metric_key] = interpret_ecg_param(metric_key, float(val))

    # -- InBody interpretations (Table 7) --
    bmi = metrics.get("bmi")
    if bmi is not None:
        interps["bmi"] = interpret_inbody_bmi(float(bmi))

    body_fat = metrics.get("bodyFat")
    if body_fat is not None and float(body_fat) > 0:
        interps["bodyFat"] = interpret_inbody_body_fat(float(body_fat))

    visceral = metrics.get("visceralFat")
    if visceral is not None:
        try:
            interps["visceralFat"] = interpret_inbody_visceral_fat(float(visceral))
        except (ValueError, TypeError):
            pass

    # -- BioWell interpretations (Tables 3 & 4) --
    bio_energy = metrics.get("bioEnergy")
    if bio_energy is not None:
        interps["bioEnergy"] = interpret_biowell_energy(float(bio_energy))

    lf_hf = metrics.get("lfhfRatio")
    if lf_hf is not None:
        interps["lfhfRatio"] = interpret_biowell_stress(float(lf_hf))

    energy_reserve = metrics.get("energyReserve")
    if energy_reserve is not None:
        er_val = float(energy_reserve)
        if er_val >= 80:
            interps["energyReserve"] = {"status": "Optimal", "interpretation": "Strong energy reserves, healthy adaptation capacity"}
        elif er_val >= 50:
            interps["energyReserve"] = {"status": "Moderate", "interpretation": "Moderate energy reserves, some depletion of adaptive capacity"}
        else:
            interps["energyReserve"] = {"status": "Low", "interpretation": "Low energy reserves, significant depletion of adaptive systems"}

    # -- Nadi parameter interpretations (Tables 1 & 2) --
    if nadi_data:
        params = nadi_data.get("health_params", {})
        nadi_interps = {}
        for param_name, param_info in params.items():
            level = param_info.get("level", "")
            if level:
                nadi_interps[param_name] = interpret_nadi_param(param_name, _level_to_pct(level))
        if nadi_interps:
            interps["nadi"] = nadi_interps

    if biowell_data:
        chakra_details = biowell_data.get("chakra_details", {})
        if chakra_details:
            interps["chakras"] = {
                key: {
                    **chakra,
                    "status": chakra.get("status")
                    or interpret_chakra(float(chakra.get("alignment_percent", 0))).get("status"),
                    "description": chakra.get("description") or get_chakra_description(key),
                }
                for key, chakra in chakra_details.items()
            }

    # -- Bioresonance system interpretations (Table 8) --
    if biores_data:
        sys_details = biores_data.get("system_details", {})
        biores_interps = {}
        for sys_name, details in sys_details.items():
            avg_pct = details.get("avg_energy_pct", 0)
            if avg_pct > 0:
                biores_interps[sys_name] = interpret_biores_energy(avg_pct)
        if biores_interps:
            interps["bioresonance"] = biores_interps

    # -- Body systems status strings --
    for sys_name, sys_data in systems.items():
        score = sys_data.get("score", 0)
        sys_data["displayStatus"] = _status_for_system_score(float(score))

    # ==================================================================
    #  DIMENSION DESCRIPTIONS -- deterministic summaries from rules
    # ==================================================================
    dimensions.setdefault("physical", {})
    _set_dimension_summary(dimensions, "physical", _build_physical_description(
        metrics, ecg_data, nadi_data, biores_data, systems
    ))

    dimensions.setdefault("psychological", {})
    _set_dimension_summary(dimensions, "psychological", _build_psychological_description(
        metrics, ecg_data, nadi_data, biowell_data
    ))

    dimensions.setdefault("emotional", {})
    _set_dimension_summary(
        dimensions,
        "emotional",
        _build_emotional_description(metrics, nadi_data, systems, biowell_data),
        _build_emotional_summary_points(nadi_data, biowell_data),
    )

    dimensions.setdefault("spiritual", {})
    _set_dimension_summary(
        dimensions,
        "spiritual",
        _build_spiritual_description(metrics, interps),
        _build_spiritual_summary_points(interps),
    )

    report["dimensions"] = dimensions
    return report


# -- Dimension description builders --

def _status_for_dimension_score(score: float) -> str:
    """Convert a dimension score into a reader-friendly Page 1 label."""
    if score >= 80:
        return "Good"
    elif score >= 60:
        return "Fair"
    elif score >= 40:
        return "Needs Attention"
    return "Critical Attention"


_CHAKRA_ORDER = [
    "muladara",
    "swadistana",
    "manipura",
    "anahatha",
    "vishudda",
    "agna",
    "sahasrara",
]


def _split_summary_points(text: str, limit: int = 4) -> list[str]:
    """Split deterministic rule prose into compact frontend bullet points."""
    chunks = re.split(r"(?<=[.!?])\s+", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()][:limit]


def _set_dimension_summary(
    dimensions: dict,
    key: str,
    description: str,
    summary_points: list[str] | None = None,
) -> None:
    """Store both prose and structured rule-backed points for a dimension."""
    dim = dimensions.setdefault(key, {})
    dim["description"] = description
    dim["summary_points"] = summary_points or _split_summary_points(description)
    dim["statusLabel"] = _status_for_dimension_score(float(dim.get("score", 0)))


def _chakra_point(chakra: dict) -> str:
    """Format a chakra line for Page 1 emotional/spiritual cards."""
    return (
        f"{chakra['name']} - {chakra['color']} "
        f"{chakra['alignment_percent']:g}% ({chakra['status']}) -- "
        f"{chakra['description']}."
    )


def _build_emotional_summary_points(nadi_data, biowell_data=None) -> list[str]:
    """Build structured Page 1 emotional points."""
    points: list[str] = []
    nadi_stress_point: str | None = None

    if nadi_data:
        params = nadi_data.get("health_params", {})
        stress_param = params.get("stress", {})
        stress = stress_param.get("level", "")
        pct = stress_param.get("percentage")
        if stress:
            value = float(pct) if pct is not None else _level_to_pct(stress)
            r = interpret_nadi_param("stress", value)
            points.append(
                f"Nadi Emotional stress {value:g}% ({stress}) -- {r['interpretation']}."
            )
            nadi_stress_point = (
                f"BioWell Stress level {value:g}% ({stress}) -- "
                f"{r['interpretation']}."
            )

    biowell_stress_point = ""
    if biowell_data:
        stress_idx = biowell_data.get("stress_index")
        stress_level = str(biowell_data.get("stress_level", "")).strip()
        if stress_idx is not None and float(stress_idx) > 0:
            value = float(stress_idx)
            r = interpret_biowell_stress(value)
            biowell_stress_point = (
                f"BioWell Stress level {value:g}x10^-2 Joules -- "
                f"{r['level']}: {r['interpretation']}."
            )
        elif stress_level and stress_level != "Low/Moderate/High":
            biowell_stress_point = f"BioWell Stress level -- {stress_level}."

        chakra = (biowell_data.get("chakra_details") or {}).get("anahatha")
        if chakra:
            points.append(_chakra_point(chakra))

    if biowell_stress_point:
        points.append(biowell_stress_point)
    elif nadi_stress_point:
        points.append(nadi_stress_point)

    return points


def _build_spiritual_summary_points(interps: dict) -> list[str]:
    """Build structured Page 1 spiritual points from chakra data."""
    chakra_info = interps.get("chakras", {})
    points: list[str] = []
    for key in _CHAKRA_ORDER:
        chakra = chakra_info.get(key)
        if chakra:
            points.append(_chakra_point(chakra))
    return points

def _build_physical_description(metrics, ecg_data, nadi_data, biores_data, systems):
    """Build Physical dimension summary from doctor rule tables."""
    parts = []

    if nadi_data:
        params = nadi_data.get("health_params", {})
        for p in ["toxin", "hydration", "flexibility"]:
            param = params.get(p, {})
            level = param.get("level", "")
            pct = param.get("percentage")
            if level:
                value = float(pct) if pct is not None else _level_to_pct(level)
                r = interpret_nadi_param(p, value)
                parts.append(
                    f"Nadi {p.capitalize()} {value:g}% ({level}) -- "
                    f"{r['interpretation']}."
                )

    if biores_data:
        sys_details = biores_data.get("system_details", {})
        concerns = []
        for sn in ["musculoskeletal", "digestive", "respiratory"]:
            detail = sys_details.get(sn, {})
            avg = detail.get("avg_energy_pct", 0)
            if 0 < avg < 60:
                r = interpret_biores_energy(avg)
                concerns.append(f"{sn} ({r['functional_status']})")
        if concerns:
            parts.append(f"Bioresonance concerns: {', '.join(concerns)}.")

    return " ".join(parts) if parts else "Physical assessment data unavailable."


def _build_psychological_description(metrics, ecg_data, nadi_data, biowell_data=None):
    """Build Psychological dimension summary from doctor rule tables."""
    parts = []

    if nadi_data:
        params = nadi_data.get("health_params", {})
        for p in ["overthinking", "stress"]:
            param = params.get(p, {})
            level = param.get("level", "")
            pct = param.get("percentage")
            if level:
                value = float(pct) if pct is not None else _level_to_pct(level)
                r = interpret_nadi_param(p, value)
                parts.append(
                    f"Nadi {p.capitalize()} {value:g}% ({level}) -- "
                    f"{r['interpretation']}."
                )

    if biowell_data:
        stress_idx = biowell_data.get("stress_index")
        if stress_idx is not None and float(stress_idx) > 0:
            value = float(stress_idx)
            r = interpret_biowell_stress(value)
            parts.append(
                f"BioWell Psychological balance between sympathetic/parasympathetic nervous system {value:g}x10^-2 Joules -- "
                f"{r['level']}: {r['interpretation']}."
            )

    return " ".join(parts) if parts else "Psychological assessment data unavailable."


def _build_emotional_description(metrics, nadi_data, systems, biowell_data=None):
    """Build Emotional dimension summary from doctor rule tables."""
    parts = []

    if nadi_data:
        params = nadi_data.get("health_params", {})
        stress_param = params.get("stress", {})
        stress = stress_param.get("level", "")
        pct = stress_param.get("percentage")
        if stress:
            value = float(pct) if pct is not None else _level_to_pct(stress)
            r = interpret_nadi_param("stress", value)
            parts.append(f"Nadi Emotional stress {value:g}% ({stress}) -- {r['interpretation']}.")

    if biowell_data:
        stress_idx = biowell_data.get("stress_index")
        if stress_idx is not None and float(stress_idx) > 0:
            value = float(stress_idx)
            r = interpret_biowell_stress(value)
            parts.append(f"BioWell Stress level {value:g}x10^-2 Joules -- {r['level']}: {r['interpretation']}.")

        stress_level = str(biowell_data.get("stress_level", "")).strip()
        if stress_level and stress_level != "Low/Moderate/High":
            parts.append(f"BioWell Stress level -- {stress_level}.")

        emotional_text = biowell_data.get("emotional_psychological")
        if emotional_text:
            parts.append(f"BioWell Emotional level -- {emotional_text}.")

        chakra = (biowell_data.get("chakra_details") or {}).get("anahatha")
        if chakra:
            parts.append(_chakra_point(chakra))

    return " ".join(parts) if parts else "Emotional assessment data unavailable."


def _build_spiritual_description(metrics, interps):
    """Build Spiritual dimension summary from doctor rule tables."""
    parts = []

    bio_energy = metrics.get("bioEnergy")
    if bio_energy is not None:
        r = interpret_biowell_energy(float(bio_energy))
        parts.append(f"BioWell Energy {bio_energy}J -- {r['status']}. {r['interpretation']}.")

    er = metrics.get("energyReserve")
    if er is not None:
        er_val = float(er)
        if er_val >= 80:
            parts.append(f"Energy Reserve {er}% -- Strong spiritual energy reserves.")
        elif er_val >= 50:
            parts.append(f"Energy Reserve {er}% -- Moderate spiritual energy.")
        else:
            parts.append(f"Energy Reserve {er}% -- Depleted spiritual energy reserves.")

    chakra_info = interps.get("chakras", {})
    if chakra_info:
        low_chakras = [name for name, data in chakra_info.items()
                       if data.get("status") in ("Moderate deviation", "Extreme")]
        if low_chakras:
            parts.append(f"Chakras needing attention: {', '.join(low_chakras)}.")
        else:
            parts.append("All chakras within healthy alignment range.")

    return " ".join(parts) if parts else "Spiritual assessment data unavailable."
