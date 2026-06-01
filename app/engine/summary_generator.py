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

    tasks = {
        "physical": _gen_physical(metrics, nadi_data, ecg_data, biores_data),
        "psychological": _gen_psychological(metrics, nadi_data, biowell_data),
        "emotional": _gen_emotional(metrics, biowell_data),
        "spiritual": _gen_spiritual(metrics, biowell_data),
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
) -> str:
    """Physical: Nadi Tarangini + ECG + BMI (InBody) + Bioresonance energy."""
    data_parts = []

    # InBody metrics
    bmi = metrics.get("bmi", 0)
    weight = metrics.get("weight", 0)
    body_fat = metrics.get("bodyFat", 0)
    if bmi or weight or body_fat:
        data_parts.append(
            f"BMI: {bmi}, Weight: {weight}kg, Body Fat: {body_fat}%"
        )

    # ECG
    hr = metrics.get("heartRate", 0)
    if hr:
        data_parts.append(f"Heart Rate: {hr} bpm")
    if ecg_data:
        ecg_vals = ecg_data.get("ecg", {})
        if ecg_vals.get("rhythm"):
            data_parts.append(f"ECG Rhythm: {ecg_vals['rhythm']}")
        if ecg_vals.get("qtc_ms"):
            data_parts.append(f"QTc: {ecg_vals['qtc_ms']}ms")
        hrv_vals = ecg_data.get("hrv", {})
        if hrv_vals.get("lf_hf_ratio"):
            data_parts.append(f"LF/HF Ratio: {hrv_vals['lf_hf_ratio']}")

    # Nadi
    if nadi_data:
        pulse = nadi_data.get("pulse", {}).get("rate_bpm", 0)
        if pulse:
            data_parts.append(f"Nadi Pulse: {pulse} bpm")
        params = nadi_data.get("health_params", {})
        for p in ["digestion", "toxin", "hydration", "flexibility", "immunity"]:
            param = params.get(p, {})
            if param.get("level"):
                data_parts.append(f"Nadi {p.title()}: {param['level']}")

    # Bioresonance energy mention
    if biores_data:
        total = biores_data.get("total_organs_scanned", 0)
        if total:
            data_parts.append(f"Bioresonance: {total} organs scanned")

    if not data_parts:
        return "Physical health data unavailable for comprehensive assessment."

    prompt = f"""Generate a 2-4 sentence PHYSICAL health summary based on this data:
{chr(10).join(f'- {d}' for d in data_parts)}

Interpretation guidelines from summary_requirement.docx:
- BMI 18.5-24.9 = Normal, 25-29.9 = Overweight, >30 = Obese
- Heart rate 60-100 bpm = Normal
- QTc >450ms (male) / >470ms (female) = Prolonged
- Nadi digestion High = excess pitta, Low = mandagni (poor digestion)
- Nadi toxin High = metabolic toxin accumulation
- Nadi flexibility Low = less joint lubrication

Write the summary in clinical prose. Do NOT use bullet points."""

    return await llm_client.generate_text(prompt, system=_CLINICAL_SYSTEM, max_tokens=300)


async def _gen_psychological(
    metrics: dict, nadi_data: dict | None, biowell_data: dict | None,
) -> str:
    """Psychological: Nadi Tarangini + BioWell stress/nervous."""
    data_parts = []

    lf_hf = metrics.get("lfhfRatio", 0)
    if lf_hf:
        data_parts.append(f"LF/HF Ratio: {lf_hf}")

    if nadi_data:
        params = nadi_data.get("health_params", {})
        for p in ["stress", "overthinking"]:
            param = params.get(p, {})
            if param.get("level"):
                data_parts.append(f"Nadi {p.title()}: {param['level']}")

    if biowell_data:
        stress_idx = biowell_data.get("stress_index")
        if stress_idx:
            data_parts.append(f"BioWell Stress Index: {stress_idx}")
        stress_level = biowell_data.get("stress_level", "")
        if stress_level and stress_level != "Low/Moderate/High":
            data_parts.append(f"BioWell Stress Level: {stress_level}")
        nervous = biowell_data.get("organ_energy_levels", {}).get("Nervous system", {})
        if nervous:
            e = nervous.get("energy level or status", nervous.get("energy", ""))
            if e:
                data_parts.append(f"Nervous System Energy: {e}")

    if not data_parts:
        return "Psychological assessment data currently unavailable."

    prompt = f"""Generate a 2-4 sentence PSYCHOLOGICAL health summary based on this data:
{chr(10).join(f'- {d}' for d in data_parts)}

Interpretation guidelines:
- Nadi stress High = locked in sympathetic state, physical stress, mental anxiety
- Nadi overthinking High = hyperactive nervous system, anxiety
- LF/HF ratio 0.8-2.5 = balanced ANS; >4.0 = high sympathetic dominance
- BioWell stress index relates to nervous system activation levels

Write the summary in clinical prose. Do NOT use bullet points."""

    return await llm_client.generate_text(prompt, system=_CLINICAL_SYSTEM, max_tokens=300)


async def _gen_emotional(metrics: dict, biowell_data: dict | None) -> str:
    """Emotional: BioWell energy reserve + organ levels."""
    data_parts = []

    er = metrics.get("energyReserve", 0)
    if er:
        data_parts.append(f"Energy Reserve: {er}%")
    be = metrics.get("bioEnergy", 0)
    if be:
        data_parts.append(f"Bio-Energy: {be} Joules")

    if biowell_data:
        organs = biowell_data.get("organ_energy_levels", {})
        for organ_name in ["Nervous system", "Immune system"]:
            entry = organs.get(organ_name, {})
            if entry:
                e = entry.get("energy level or status", entry.get("energy", ""))
                s = entry.get("status", "")
                if e:
                    data_parts.append(f"{organ_name}: energy={e}, status={s}")

    if not data_parts:
        return "Emotional wellness data currently unavailable."

    prompt = f"""Generate a 2-4 sentence EMOTIONAL health summary based on this data:
{chr(10).join(f'- {d}' for d in data_parts)}

Interpretation guidelines:
- Energy reserve >80% = high emotional resilience
- Energy reserve 50-80% = moderate emotional stability
- Energy reserve <50% = emotional depletion, burnout risk
- Bio-Energy indicates overall vital energy for emotional regulation
- Nervous system energy reflects emotional processing capacity

Write the summary in clinical prose. Do NOT use bullet points."""

    return await llm_client.generate_text(prompt, system=_CLINICAL_SYSTEM, max_tokens=300)


async def _gen_spiritual(metrics: dict, biowell_data: dict | None) -> str:
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

Interpretation guidelines:
- 7 chakras represent energy centers from root (grounding) to crown (consciousness)
- Good alignment = balanced energy flow
- Misalignment indicates blocked or overactive energy in that center
- Root chakra relates to stability, Heart to love/compassion, Crown to spiritual connection
- Overall bio-energy reflects spiritual vitality and life force

Write the summary in clinical prose. Do NOT use bullet points."""

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

        # Collect relevant organ energies
        organ_data = []
        mapped_organs = BIOWELL_ORGAN_SYSTEM_MAP.get(sys_key, [])
        for organ_name in mapped_organs:
            if organ_name in organs:
                entry = organs[organ_name]
                e = entry.get("energy level or status", entry.get("energy", ""))
                s = entry.get("status", "")
                if e:
                    organ_data.append(f"{organ_name}: energy={e}, status={s}")

        # Add nadi organ health if available
        nadi_organ_info = ""
        if nadi_data:
            nadi_organs = nadi_data.get("organ_health", {})
            for organ_name, info in nadi_organs.items():
                if _organ_matches_system(organ_name, sys_key):
                    nadi_organ_info += f"Nadi: {organ_name} = {info.get('status', '')}\n"

        tasks[sys_key] = _gen_system_summary(
            display_name, score, status, organ_data, nadi_organ_info
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
    display_name: str, score: int, status: str,
    organ_data: list, nadi_info: str,
) -> str:
    """Generate a 1-2 sentence summary for one body system."""
    data_text = ""
    if organ_data:
        data_text = "\n".join(f"- {d}" for d in organ_data)
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
