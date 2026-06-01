"""Fix interpretation.py: rewrite lines 354+ with complete build_interpretations."""
from pathlib import Path

fpath = Path(r"app/engine/interpretation.py")
lines = fpath.read_text(encoding="utf-8").splitlines(keepends=True)

# Keep lines 1-353 (index 0-352), replace everything from 354 onwards
head = lines[:353]

tail = '''

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
    dimensions["physical"]["description"] = _build_physical_description(
        metrics, ecg_data, nadi_data, biores_data, systems
    )

    dimensions.setdefault("psychological", {})
    dimensions["psychological"]["description"] = _build_psychological_description(
        metrics, ecg_data, nadi_data
    )

    dimensions.setdefault("emotional", {})
    dimensions["emotional"]["description"] = _build_emotional_description(
        metrics, nadi_data, systems
    )

    dimensions.setdefault("spiritual", {})
    dimensions["spiritual"]["description"] = _build_spiritual_description(
        metrics, interps
    )

    report["dimensions"] = dimensions
    return report


# -- Dimension description builders --

def _build_physical_description(metrics, ecg_data, nadi_data, biores_data, systems):
    """Build Physical dimension summary from doctor rule tables."""
    parts = []

    bmi = metrics.get("bmi")
    if bmi is not None:
        r = interpret_inbody_bmi(float(bmi))
        parts.append(f"BMI {bmi} kg/m2 -- {r['status']}: {r['interpretation']}.")

    hr = metrics.get("heartRate")
    if hr is not None:
        r = interpret_ecg_param("heart_rate", float(hr))
        parts.append(f"Heart Rate {hr} bpm -- {r['status']}.")
        if r["status"] != "Normal":
            parts.append(f"Possible cause: {r['interpretation']}.")

    if ecg_data:
        qtc = ecg_data.get("ecg", {}).get("qtc_interval_ms")
        if qtc and float(qtc) > 0:
            r = interpret_ecg_param("qtc_interval", float(qtc))
            if r["status"] != "Normal":
                parts.append(f"QTc {qtc} ms -- {r['status']}: {r['interpretation']}.")

    if nadi_data:
        params = nadi_data.get("health_params", {})
        for p in ["digestion", "toxin", "hydration", "immunity", "flexibility"]:
            param = params.get(p, {})
            level = param.get("level", "")
            if level:
                r = interpret_nadi_param(p, _level_to_pct(level))
                parts.append(f"Nadi {p.capitalize()} ({level}) -- {r['interpretation']}.")

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


def _build_psychological_description(metrics, ecg_data, nadi_data):
    """Build Psychological dimension summary from doctor rule tables."""
    parts = []

    lf_hf = metrics.get("lfhfRatio")
    if lf_hf is not None:
        r = interpret_biowell_stress(float(lf_hf))
        parts.append(f"LF/HF Ratio {lf_hf} -- Stress level: {r['level']}. {r['interpretation']}.")

    if ecg_data:
        hrv = ecg_data.get("hrv", {})
        sdnn = hrv.get("sdnn_ms")
        if sdnn and float(sdnn) > 0:
            v = float(sdnn)
            if v < 50:
                parts.append(f"SDNN {v} ms -- Low HRV, reduced autonomic flexibility and higher stress load.")
            elif v <= 100:
                parts.append(f"SDNN {v} ms -- Moderate HRV, adequate autonomic regulation.")
            else:
                parts.append(f"SDNN {v} ms -- Good HRV, strong autonomic nervous system adaptability.")

    if nadi_data:
        params = nadi_data.get("health_params", {})
        for p in ["stress", "overthinking"]:
            param = params.get(p, {})
            level = param.get("level", "")
            if level:
                r = interpret_nadi_param(p, _level_to_pct(level))
                parts.append(f"Nadi {p.capitalize()} ({level}) -- {r['interpretation']}.")

    return " ".join(parts) if parts else "Psychological assessment data unavailable."


def _build_emotional_description(metrics, nadi_data, systems):
    """Build Emotional dimension summary from doctor rule tables."""
    parts = []

    er = metrics.get("energyReserve")
    if er is not None:
        er_val = float(er)
        if er_val >= 80:
            parts.append(f"Energy Reserve {er}% -- Optimal. Strong adaptive capacity and emotional resilience.")
        elif er_val >= 50:
            parts.append(f"Energy Reserve {er}% -- Moderate. Some emotional fatigue may be present.")
        else:
            parts.append(f"Energy Reserve {er}% -- Low. Significant emotional depletion and reduced coping.")

    nervous = systems.get("nervous", {})
    ns_score = nervous.get("score", 0)
    if ns_score > 0:
        ns_status = _status_for_system_score(ns_score)
        parts.append(f"Nervous System score {ns_score} -- {ns_status}.")

    if nadi_data:
        params = nadi_data.get("health_params", {})
        stress = params.get("stress", {}).get("level", "")
        if stress:
            r = interpret_nadi_param("stress", _level_to_pct(stress))
            parts.append(f"Nadi Stress ({stress}) -- {r['interpretation']}.")

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
'''

fpath.write_text("".join(head) + tail, encoding="utf-8")
print(f"[OK] interpretation.py rewritten. Total lines: {len((''.join(head) + tail).splitlines())}")
