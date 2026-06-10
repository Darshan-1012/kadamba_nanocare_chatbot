"""AI-powered clinical summary generator.

Generates narrative prose summaries for each report dimension, body system,
and SWOT analysis using the stronger OLLAMA_SUMMARY_MODEL.

Each summary receives the ACTUAL parsed device data as context, plus
deterministic rules from summary_requirement.docx to guide interpretation.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Optional

from app.engine import llm_client
from app.engine.interpretation import interpret_biowell_energy

log = logging.getLogger(__name__)

# ── System prompt for all clinical summaries ─────────────────────────
_CLINICAL_SYSTEM = """You are a clinical wellness report writer for Nanocare.
Write concise, professional clinical summaries using the provided device data.
Rules:
- Write in 3rd person ("The patient shows...")
- Be factual — only reference data that is actually provided
- Keep each summary to 2-4 sentences maximum
- Use clinical but accessible language
- Include specific numeric values where available
- Do NOT invent data or make assumptions about missing values
- Do NOT add disclaimers or meta-commentary"""


def _find_biowell_entries(organs, organ_name: str) -> list[dict]:
    """Return BioWell entries for an organ from old dict or new list data."""
    if isinstance(organs, dict):
        entry = organs.get(organ_name)
        return [entry] if isinstance(entry, dict) else []

    if isinstance(organs, list):
        matches = []
        for entry in organs:
            if not isinstance(entry, dict):
                continue
            name = (
                entry.get("organ")
                or entry.get("organ_name")
                or entry.get("name")
                or entry.get("system")
                or ""
            )
            if name == organ_name:
                matches.append(entry)
        return matches

    return []


def _biowell_entry_summary_value(entry: dict):
    """Prefer Balance% for state text, but preserve Energy Joules if present."""
    balance = (
        entry.get("balance_percent")
        or entry.get("balance")
        or entry.get("balance_pct")
    )
    legacy = entry.get("energy level or status")
    if balance is None and legacy is not None and float(legacy) > 10:
        balance = legacy
    energy = entry.get("energy_joules") or entry.get("energy")
    return balance, energy


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DIMENSION SUMMARIES (Page 1)                                      ║
# ╚══════════════════════════════════════════════════════════════════════╝

async def generate_dimension_summaries(
    report: dict,
    nadi_data: dict | None = None,
    ecg_data: dict | None = None,
    biowell_data: dict | None = None,
    biores_data: dict | None = None,
) -> Dict[str, str]:
    """Generate AI summaries for all 4 dimensions in parallel.

    Returns:
        Dict with keys: physical, psychological, emotional, spiritual
        Each value is a 2-4 sentence clinical summary.
    """
    metrics = report.get("metrics", {})
    dimensions = report.get("dimensions", {})

    tasks = {
        "physical": _gen_physical(
            metrics, nadi_data, ecg_data, biores_data,
            dimensions.get("physical", {}).get("description", ""),
        ),
        "psychological": _gen_psychological(
            metrics, nadi_data, biowell_data,
            dimensions.get("psychological", {}).get("description", ""),
        ),
        "emotional": _gen_emotional(
            metrics, biowell_data,
            dimensions.get("emotional", {}).get("description", ""),
        ),
        "spiritual": _gen_spiritual(
            metrics, biowell_data,
            dimensions.get("spiritual", {}).get("description", ""),
        ),
    }

    results = {}
    gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for key, result in zip(tasks.keys(), gathered):
        if isinstance(result, Exception):
            log.error(f"Summary generation failed for {key}: {result}")
            results[key] = f"Summary generation unavailable."
        else:
            results[key] = result

    return results


async def _gen_physical(
    metrics: dict, nadi_data: dict | None,
    ecg_data: dict | None, biores_data: dict | None,
    rule_summary: str = "",
) -> str:
    """Physical: LF/HF + selected Nadi physical health parameters."""
    data_parts = []

    lf_hf = metrics.get("lfhfRatio", 0)
    if lf_hf:
        data_parts.append(f"LF/HF Ratio: {lf_hf}")
    if ecg_data:
        hrv_vals = ecg_data.get("hrv", {})
        if hrv_vals.get("lf_hf_ratio") and not lf_hf:
            data_parts.append(f"LF/HF Ratio: {hrv_vals['lf_hf_ratio']}")

    # Nadi
    if nadi_data:
        params = nadi_data.get("health_params", {})
        for p in ["toxin", "hydration", "flexibility"]:
            param = params.get(p, {})
            if param.get("level"):
                pct = param.get("percentage")
                value = f" ({pct}%)" if pct is not None else ""
                data_parts.append(f"Nadi {p.title()}: {param['level']}{value}")

    if not data_parts:
        return "Physical health data unavailable for comprehensive assessment."

    prompt = f"""Generate a 2-4 sentence PHYSICAL health summary based on this data:
{chr(10).join(f'- {d}' for d in data_parts)}

Doctor-rule interpretation from summary_requirement.docx. Treat this as the source of truth:
{rule_summary or 'No deterministic interpretation available.'}

Interpretation guidelines:
- LF/HF 0.8-2.5 = balanced autonomic state; >4.0 = high sympathetic load
- Nadi toxin High = high metabolic toxin accumulation; Low = efficient metabolism
- Nadi hydration High = electrolyte balance and toxin removal; Low = cellular dehydration and toxin accumulation
- Nadi flexibility High = optimal lubricated joints; Low = less lubrication and restricted range of motion

Write a comprehensive clinical prose summary. Do not contradict the doctor-rule interpretation. Do NOT use bullet points."""

    return await llm_client.generate_text(prompt, system=_CLINICAL_SYSTEM, max_tokens=300)


async def _gen_psychological(
    metrics: dict, nadi_data: dict | None, biowell_data: dict | None,
    rule_summary: str = "",
) -> str:
    """Psychological: Nadi overthinking/stress + BioWell stress index."""
    data_parts = []

    if nadi_data:
        params = nadi_data.get("health_params", {})
        for p in ["overthinking", "stress"]:
            param = params.get(p, {})
            if param.get("level"):
                pct = param.get("percentage")
                value = f" ({pct}%)" if pct is not None else ""
                data_parts.append(f"Nadi {p.title()}: {param['level']}{value}")

    if biowell_data:
        stress_idx = biowell_data.get("stress_index")
        if stress_idx:
            data_parts.append(
                "BioWell balance between sympathetic/parasympathetic nervous "
                f"system: {stress_idx}x10^-2 Joules"
            )
        stress_level = biowell_data.get("stress_level", "")
        if stress_level and stress_level != "Low/Moderate/High":
            data_parts.append(f"BioWell Stress Level: {stress_level}")

    if not data_parts:
        return "Psychological assessment data currently unavailable."

    prompt = f"""Generate a 2-4 sentence PSYCHOLOGICAL health summary based on this data:
{chr(10).join(f'- {d}' for d in data_parts)}

Doctor-rule interpretation from summary_requirement.docx. Treat this as the source of truth:
{rule_summary or 'No deterministic interpretation available.'}

Interpretation guidelines:
- Nadi stress High = locked in sympathetic state, physical stress, mental anxiety
- Nadi overthinking High = hyperactive nervous system, anxiety
- BioWell balance between sympathetic/parasympathetic nervous system 0-1.5x10^-2 Joules = Optimal
- BioWell balance between sympathetic/parasympathetic nervous system 1.5-2.3x10^-2 Joules = Medium temporary adaptation
- BioWell balance between sympathetic/parasympathetic nervous system >=2.3x10^-2 Joules = High adaptation to extreme conditions or internal problems

Write a comprehensive clinical prose summary. Do not contradict the doctor-rule interpretation. Do NOT use bullet points."""

    return await llm_client.generate_text(prompt, system=_CLINICAL_SYSTEM, max_tokens=300)


async def _gen_emotional(
    metrics: dict,
    biowell_data: dict | None,
    rule_summary: str = "",
) -> str:
    """Emotional: Nadi stress + BioWell emotional/stress indicators."""
    data_parts = []

    # Nadi emotional stress
    # nadi_data is not part of this function signature, so deterministic
    # Nadi stress is supplied through rule_summary from interpretation.py.

    if biowell_data:
        stress_idx = biowell_data.get("stress_index")
        if stress_idx:
            data_parts.append(f"BioWell Emotional Stress Index: {stress_idx}x10^-2 Joules")
        stress_level = biowell_data.get("stress_level", "")
        if stress_level and stress_level != "Low/Moderate/High":
            data_parts.append(f"BioWell Emotional Stress Level: {stress_level}")
        emotional_text = biowell_data.get("emotional_psychological")
        if emotional_text:
            data_parts.append(f"BioWell Emotional/Psychological: {emotional_text}")

    if not data_parts:
        return "Emotional wellness data currently unavailable."

    prompt = f"""Generate a 2-4 sentence EMOTIONAL health summary based on this data:
{chr(10).join(f'- {d}' for d in data_parts)}

Doctor-rule interpretation from summary_requirement.docx. Treat this as the source of truth:
{rule_summary or 'No deterministic interpretation available.'}

Interpretation guidelines:
- Use Nadi stress level as the emotional stress marker when present in the doctor-rule interpretation.
- Use BioWell emotional/stress level or BioWell emotional/psychological text when present.
- Do not mention energy reserve, nervous system score, BMI, or heart rate in the emotional quadrant summary.

Write a comprehensive clinical prose summary. Do not contradict the doctor-rule interpretation. Do NOT use bullet points."""

    return await llm_client.generate_text(prompt, system=_CLINICAL_SYSTEM, max_tokens=300)


async def _gen_spiritual(
    metrics: dict,
    biowell_data: dict | None,
    rule_summary: str = "",
) -> str:
    """Spiritual: BioWell chakra alignment data."""
    data_parts = []

    be = metrics.get("bioEnergy", 0)
    if be:
        data_parts.append(f"Bio-Energy: {be} Joules")
    er = metrics.get("energyReserve", 0)
    if er:
        data_parts.append(f"Energy Reserve: {er}%")

    if biowell_data:
        chakras = biowell_data.get("chakra_alignment", {})
        if chakras:
            chakra_names = ["root", "sacral", "solar_plexus", "heart",
                           "throat", "third_eye", "crown"]
            for c in chakra_names:
                ch = chakras.get(c, {})
                alignment = ch.get("alignment", "")
                energy = ch.get("energy", "")
                if alignment:
                    label = c.replace("_", " ").title()
                    parts = [f"alignment={alignment}"]
                    if energy:
                        parts.append(f"energy={energy}")
                    data_parts.append(f"{label} Chakra: {', '.join(parts)}")

    if not data_parts:
        return "Spiritual wellness assessment data currently unavailable."

    prompt = f"""Generate a 2-4 sentence SPIRITUAL health summary based on this data:
{chr(10).join(f'- {d}' for d in data_parts)}

Doctor-rule interpretation from summary_requirement.docx. Treat this as the source of truth:
{rule_summary or 'No deterministic interpretation available.'}

Interpretation guidelines:
- 7 chakras represent energy centers from root (grounding) to crown (consciousness)
- Good alignment = balanced energy flow
- Misalignment indicates blocked or overactive energy in that center
- Root chakra relates to stability, Heart to love/compassion, Crown to spiritual connection
- Overall bio-energy reflects spiritual vitality and life force

Write a comprehensive clinical prose summary. Do not contradict the doctor-rule interpretation. Do NOT use bullet points."""

    return await llm_client.generate_text(prompt, system=_CLINICAL_SYSTEM, max_tokens=300)


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  BODY SYSTEM SUMMARIES (Page 2)                                    ║
# ╚══════════════════════════════════════════════════════════════════════╝

_SYSTEM_DISPLAY_NAMES = {
    "nervous": "Nervous System",
    "cardiovascular": "Cardiovascular System",
    "respiratory": "Respiratory System",
    "musculoskeletal": "Musculoskeletal System",
    "digestive": "Digestive System",
    "integumentary": "Integumentary System",
    "endocrine": "Endocrine System",
    "urogenital": "Urogenital System",
    "reproductive": "Reproductive System",
    "immune": "Immune System",
}

_SYSTEM_ENERGY_INTERPRETATIONS = {
    "nervous": {
        "very low energy": "for the nervous system, this can reflect reduced neural reserve, poor stress recovery, autonomic fatigue, and lower adaptive capacity",
        "low energy": "for the nervous system, this can point to mental fatigue, reduced resilience to stress, weaker autonomic compensation, and slower recovery",
        "optimal energy": "for the nervous system, this supports balanced autonomic regulation, stable stress response, and efficient neural adaptation",
        "increased energy": "for the nervous system, this can reflect heightened neural activation, sympathetic load, overthinking, sleep strain, or stress-response activity",
        "heightened energy": "for the nervous system, this can suggest marked neural overactivation, strong stress load, autonomic strain, or difficulty down-regulating",
    },
    "cardiovascular": {
        "very low energy": "for the cardiovascular system, this can reflect reduced circulatory reserve, weak vascular adaptation, and lower functional support to tissues",
        "low energy": "for the cardiovascular system, this can point to reduced cardiac-circulatory efficiency, fatigue tendency, and weaker adaptive compensation",
        "optimal energy": "for the cardiovascular system, this supports steady circulatory tone, balanced vascular response, and efficient energy distribution",
        "increased energy": "for the cardiovascular system, this can reflect circulatory load, vascular tension, stress-related cardiac demand, or increased adaptive effort",
        "heightened energy": "for the cardiovascular system, this can suggest significant vascular or cardiac stress load and stronger strain on adaptation mechanisms",
    },
    "respiratory": {
        "very low energy": "for the respiratory system, this can reflect reduced respiratory reserve, weaker oxygenation support, and low adaptive capacity",
        "low energy": "for the respiratory system, this can point to breathing fatigue, lower respiratory efficiency, or reduced ability to compensate under load",
        "optimal energy": "for the respiratory system, this supports efficient breathing mechanics, balanced oxygen exchange, and stable respiratory adaptation",
        "increased energy": "for the respiratory system, this can reflect respiratory workload, airway irritation tendency, increased oxygen demand, or stress-linked breathing activation",
        "heightened energy": "for the respiratory system, this can suggest strong respiratory strain, airway stress, or possible inflammatory activation in the breathing pathway",
    },
    "musculoskeletal": {
        "very low energy": "for the musculoskeletal system, this can reflect reduced structural reserve, poor recovery capacity, and low support for muscles, joints, or spine",
        "low energy": "for the musculoskeletal system, this can point to fatigue tendency, reduced tissue recovery, joint stiffness, or weaker postural compensation",
        "optimal energy": "for the musculoskeletal system, this supports balanced muscle tone, joint adaptation, and efficient structural recovery",
        "increased energy": "for the musculoskeletal system, this can reflect muscle tension, spinal or joint load, recovery demand, or overuse-related activation",
        "heightened energy": "for the musculoskeletal system, this can suggest marked structural strain, high tissue stress, or inflammation-related activation",
    },
    "digestive": {
        "very low energy": "for the digestive system, this can reflect weak digestive reserve, low metabolic support, and reduced ability to process or assimilate nutrients",
        "low energy": "for the digestive system, this can point to digestive sluggishness, reduced enzyme or metabolic activity, fatigue after meals, or low gut adaptation",
        "optimal energy": "for the digestive system, this supports balanced digestive workload, stable metabolism, and efficient nutrient processing",
        "increased energy": "for the digestive system, this can reflect digestive workload, gut irritation tendency, liver or pancreatic demand, or metabolic activation",
        "heightened energy": "for the digestive system, this can suggest strong digestive stress, inflammatory tendency, or high load on liver, pancreas, or intestinal function",
    },
    "integumentary": {
        "very low energy": "for the integumentary system, this can reflect reduced skin barrier vitality, weak tissue repair, and lower thermoregulation support",
        "low energy": "for the integumentary system, this can point to slower skin recovery, reduced barrier strength, dryness tendency, or lower peripheral vitality",
        "optimal energy": "for the integumentary system, this supports healthy skin barrier activity, tissue repair, and balanced peripheral circulation",
        "increased energy": "for the integumentary system, this can reflect skin barrier stress, heat or inflammatory activation, or increased repair demand",
        "heightened energy": "for the integumentary system, this can suggest significant skin or tissue stress, inflammatory activity, or heightened repair demand",
    },
    "endocrine": {
        "very low energy": "for the endocrine system, this can reflect weak hormonal reserve, reduced stress-axis support, and lower metabolic regulation capacity",
        "low energy": "for the endocrine system, this can point to hormonal fatigue, reduced thyroid or pancreatic support, adrenal strain, or slower metabolic adaptation",
        "optimal energy": "for the endocrine system, this supports balanced hormonal signaling, stable metabolism, and efficient stress adaptation",
        "increased energy": "for the endocrine system, this can reflect hormonal adaptation load, stress-axis activation, thyroid or pancreatic demand, or energy-regulation strain",
        "heightened energy": "for the endocrine system, this can suggest strong hormonal stress, hyper-reactive adaptation, or significant demand on endocrine regulation",
    },
    "urogenital": {
        "very low energy": "for the urogenital system, this can reflect reduced kidney or urinary reserve, weaker fluid regulation, and low pelvic adaptive support",
        "low energy": "for the urogenital system, this can point to kidney or urinary fatigue, reduced detoxification support, or weaker fluid-balance compensation",
        "optimal energy": "for the urogenital system, this supports balanced kidney function, urinary regulation, and stable fluid-energy management",
        "increased energy": "for the urogenital system, this can reflect kidney workload, urinary tract stress, fluid-regulation demand, or pelvic-system activation",
        "heightened energy": "for the urogenital system, this can suggest significant kidney or urinary stress, inflammatory tendency, or high pelvic-system load",
    },
    "reproductive": {
        "very low energy": "for the reproductive system, this can reflect reduced reproductive reserve, weaker pelvic vitality, and lower hormonal support",
        "low energy": "for the reproductive system, this can point to reduced reproductive vitality, pelvic fatigue, hormonal strain, or weaker functional compensation",
        "optimal energy": "for the reproductive system, this supports stable reproductive vitality, balanced pelvic energy, and coordinated hormonal support",
        "increased energy": "for the reproductive system, this can reflect pelvic workload, prostate or reproductive tissue activation, hormonal demand, or adaptive strain",
        "heightened energy": "for the reproductive system, this can suggest marked pelvic or reproductive stress, inflammatory tendency, or strong hormonal-system load",
    },
    "immune": {
        "very low energy": "for the immune system, this can reflect weak immune reserve, reduced defense capacity, and lower recovery support",
        "low energy": "for the immune system, this can point to immune fatigue, reduced resilience, slower recovery, or weaker adaptation after stress",
        "optimal energy": "for the immune system, this supports balanced immune surveillance, healthy recovery, and stable defense regulation",
        "increased energy": "for the immune system, this can reflect active immune surveillance, recovery demand, inflammatory signaling, or heightened defense response",
        "heightened energy": "for the immune system, this can suggest significant immune activation, inflammatory load, or strong stress on defense regulation",
    },
}


async def generate_system_summaries(
    report: dict,
    biowell_data: dict | None = None,
    nadi_data: dict | None = None,
) -> Dict[str, str]:
    """Generate 1-2 sentence summaries for each body system.

    Returns:
        Dict mapping system key → summary text.
    """
    systems = report.get("systems", {})
    organs = {}
    if biowell_data:
        organs = biowell_data.get("organ_energy_levels", {})

    # Build per-system organ data
    from app.engine.scoring import BIOWELL_ORGAN_SYSTEM_MAP

    tasks = {}
    for sys_key, display_name in _SYSTEM_DISPLAY_NAMES.items():
        score = systems.get(sys_key, {}).get("score", 50)
        status = systems.get(sys_key, {}).get("status", "Need Attention")

        # Collect relevant BioWell rows. New extraction returns a list to
        # preserve duplicate table rows; old cached extraction used a dict.
        organ_data = []
        mapped_organs = set(BIOWELL_ORGAN_SYSTEM_MAP.get(sys_key, []))
        from app.engine.scoring import (
            BIOWELL_SYSTEM_GROUP_MAP,
            _biowell_entry_group,
            _iter_biowell_organ_rows,
        )
        rows = list(_iter_biowell_organ_rows(organs))
        mapped_groups = set(BIOWELL_SYSTEM_GROUP_MAP.get(sys_key, []))

        def _append_biowell_row(organ_name: str, entry) -> None:
            if isinstance(entry, dict):
                balance = (
                    entry.get("balance_percent")
                    or entry.get("balance")
                    or entry.get("balance_pct")
                )
                legacy = entry.get("energy level or status")
                if balance is None and legacy is not None and float(legacy) > 10:
                    balance = legacy
                energy = entry.get("energy_joules") or entry.get("energy")
                status_text = entry.get("status", "")
            else:
                value = float(entry)
                balance = value if value > 10 else None
                energy = value if value <= 10 else None
                status_text = ""

            if balance is not None or energy is not None:
                organ_data.append({
                    "organ": organ_name,
                    "balance_percent": float(balance) if balance is not None else None,
                    "energy_joules": float(energy) if energy is not None else None,
                    "status": status_text,
                })

        for organ_name, entry in rows:
            if _biowell_entry_group(entry) in mapped_groups:
                _append_biowell_row(organ_name, entry)

        if not organ_data:
            for organ_name, entry in rows:
                if organ_name in mapped_organs:
                    _append_biowell_row(organ_name, entry)

        if not organ_data and sys_key == "reproductive":
            for organ_name, entry in rows:
                if organ_name == "Prostate":
                    _append_biowell_row(organ_name, entry)

        # Add nadi organ health if available
        nadi_organ_info = ""
        if nadi_data:
            nadi_organs = nadi_data.get("organ_health", {})
            for organ_name, info in nadi_organs.items():
                if _organ_matches_system(organ_name, sys_key):
                    nadi_organ_info += f"Nadi: {organ_name} = {info.get('status', '')}\n"

        tasks[sys_key] = _gen_system_summary(
            sys_key, display_name, score, status, organ_data, nadi_organ_info
        )

    results = {}
    gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for key, result in zip(tasks.keys(), gathered):
        if isinstance(result, Exception):
            log.error(f"System summary failed for {key}: {result}")
            results[key] = f"Assessment data unavailable."
        else:
            results[key] = result

    return results


def _organ_matches_system(organ_name: str, sys_key: str) -> bool:
    """Check if a Nadi organ name belongs to a body system."""
    organ_lower = organ_name.lower()
    mapping = {
        "digestive": ["liver", "stomach", "intestin", "colon", "pancreas",
                       "gallbladder", "digest"],
        "cardiovascular": ["heart", "cardio"],
        "respiratory": ["lung", "bronch", "trachea", "respirat"],
        "nervous": ["brain", "nerve", "nervous"],
        "musculoskeletal": ["spine", "bone", "muscle", "joint", "skeletal"],
        "endocrine": ["thyroid", "adrenal", "pituitary", "endocrin"],
        "urogenital": ["kidney", "bladder", "urinary", "urogen"],
        "immune": ["immune", "spleen", "lymph"],
        "reproductive": ["prostate", "uterus", "ovary", "reproduct"],
        "integumentary": ["skin", "hair", "nail"],
    }
    keywords = mapping.get(sys_key, [])
    return any(kw in organ_lower for kw in keywords)


async def _gen_system_summary(
    sys_key: str, display_name: str, score: int, status: str,
    organ_data: list, nadi_info: str,
) -> str:
    """Generate a 1-2 sentence summary for one body system."""
    balance_values = []
    energy_values = []
    for item in organ_data:
        if isinstance(item, dict):
            balance = item.get("balance_percent")
            energy = item.get("energy_joules")
            if balance is not None:
                balance_values.append(float(balance))
            if energy is not None:
                energy_values.append(float(energy))
            continue

        try:
            raw_value = float(str(item).split("energy=")[1].split(",")[0])
        except (IndexError, ValueError):
            continue
        if raw_value > 10:
            balance_values.append(raw_value)
        elif raw_value > 0:
            energy_values.append(raw_value)

    avg_balance = sum(balance_values) / len(balance_values) if balance_values else None
    avg_energy = sum(energy_values) / len(energy_values) if energy_values else None

    if avg_balance is not None:
        state, _meaning = _balance_state(avg_balance)
        summary = f"Balance is {avg_balance:.1f}%, indicating {state}."
        if avg_energy is not None:
            energy_rule = interpret_biowell_energy(avg_energy)
            energy_detail = _system_energy_interpretation(sys_key, energy_rule)
            summary += (
                f" Energy is {avg_energy:.2f} Joules (x10^-2), which falls under "
                f"{energy_rule['status'].lower()}; {energy_detail}."
            )
        return summary

    if avg_energy is not None:
        energy_rule = interpret_biowell_energy(avg_energy)
        energy_detail = _system_energy_interpretation(sys_key, energy_rule)
        return (
            f"The BioWell functional table shows average energy "
            f"of {avg_energy:.2f} Joules (x10-2), classified as "
            f"{energy_rule['status']}. {energy_detail.capitalize()} "
            f"The current system score is {score}%."
        )

    data_text = ""
    if organ_data:
        rows = []
        for d in organ_data:
            if isinstance(d, dict):
                rows.append(
                    f"- {d.get('organ')}: balance={d.get('balance_percent')}, "
                    f"energy={d.get('energy_joules')}"
                )
            else:
                rows.append(f"- {d}")
        data_text = "\n".join(rows)
    if nadi_info:
        data_text += f"\n{nadi_info}"

    if not data_text.strip():
        if score >= 70:
            return f"{display_name} shows normal function with score {score}%."
        else:
            return f"{display_name} needs attention with score {score}%."

    prompt = f"""Generate a 1-2 sentence clinical summary for the {display_name}.
Overall score: {score}% ({status})

Device data:
{data_text}

Interpretation: Score >70 = Normal function, 50-70 = Needs attention, <50 = Significant concern.
BioWell energy 4-7 = Normal, <4 = Low, >7 = Increased/overactive.

Write one concise clinical sentence. No bullet points."""

    return await llm_client.generate_text(prompt, system=_CLINICAL_SYSTEM, max_tokens=150)


def _balance_state(balance: float) -> tuple[str, str]:
    """Explain BioWell Balance% in patient-facing language."""
    if balance >= 80:
        return (
            "good left-right energetic balance",
            "This suggests the related organs are functioning with stable energetic coordination.",
        )
    if balance >= 60:
        return (
            "moderate balance",
            "This suggests mild variation across the organ group and is worth supporting with routine care.",
        )
    if balance >= 40:
        return (
            "noticeable imbalance",
            "This suggests the system may be under functional stress and should be watched closely.",
        )
    return (
        "significant imbalance",
        "This suggests reduced energetic coordination and a stronger need for corrective support.",
    )


def _system_energy_interpretation(sys_key: str, energy_rule: dict) -> str:
    """Return system-specific wording for a BioWell energy range."""
    status = str(energy_rule.get("status", "")).lower()
    system_rules = _SYSTEM_ENERGY_INTERPRETATIONS.get(sys_key, {})
    detail = system_rules.get(status)
    if detail:
        return detail
    return str(energy_rule.get("interpretation", "")).strip()


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  SWOT SUMMARY (Page 4)                                             ║
# ╚══════════════════════════════════════════════════════════════════════╝

async def generate_swot_summary(dmit_data: dict | None) -> dict:
    """Generate SWOT analysis text from DMIT data.

    Returns:
        Dict with keys: strengths, weaknesses, opportunities, threats
        Each value is a formatted text string.
    """
    if not dmit_data:
        return {
            "strengths": "DMIT analysis not available.",
            "weaknesses": "DMIT analysis not available.",
            "opportunities": "DMIT analysis not available.",
            "threats": "DMIT analysis not available.",
        }

    swot = dmit_data.get("swot", {})
    return {
        "strengths": "\n".join(f"• {s}" for s in swot.get("strengths", [])) or "Not available",
        "weaknesses": "\n".join(f"• {w}" for w in swot.get("weaknesses", [])) or "Not available",
        "opportunities": "\n".join(f"• {o}" for o in swot.get("opportunities", [])) or "Not available",
        "threats": "\n".join(f"• {t}" for t in swot.get("threats", [])) or "Not available",
    }


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  ORCHESTRATOR                                                       ║
# ╚══════════════════════════════════════════════════════════════════════╝

async def generate_all_summaries(
    report: dict,
    nadi_data: dict | None = None,
    ecg_data: dict | None = None,
    biowell_data: dict | None = None,
    biores_data: dict | None = None,
    dmit_data: dict | None = None,
) -> dict:
    """Generate all AI summaries in parallel.

    Returns a dict with:
        - dimension_summaries: {physical, psychological, emotional, spiritual}
        - system_summaries: {nervous, cardiovascular, ..., immune}
        - swot: {strengths, weaknesses, opportunities, threats}
    """
    log.info("Generating AI summaries (parallel)...")

    dim_task = generate_dimension_summaries(
        report, nadi_data=nadi_data, ecg_data=ecg_data,
        biowell_data=biowell_data, biores_data=biores_data,
    )
    sys_task = generate_system_summaries(
        report, biowell_data=biowell_data, nadi_data=nadi_data,
    )
    swot_task = generate_swot_summary(dmit_data)

    dim_summaries, sys_summaries, swot = await asyncio.gather(
        dim_task, sys_task, swot_task,
    )

    log.info(
        f"AI summaries complete: {len(dim_summaries)} dimensions, "
        f"{len(sys_summaries)} systems"
    )

    return {
        "dimension_summaries": dim_summaries,
        "system_summaries": sys_summaries,
        "swot": swot,
    }
