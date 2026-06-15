"""Multi-step report synthesizer — parallel extraction with caching.

Architecture:
  Step 1: Parse Bioresonance/ECG/HRV/Nadi directly (NO LLM) → deterministic
  Step 2: Extract text from other files (CPU) → cache raw text
  Step 3: Compress text → cache compressed text
  Step 4: LLM extraction for InBody + BioWell (PARALLEL) → cache results
  Step 5: LLM synthesis with deterministic scores injected → final report
"""
import asyncio
import json
import logging
import os
import re
import time

from app.engine.biorhythm_extractor import extract_biorhythm_image
from app.engine.biorhythm_calculator import build_biorhythm_calendar
from pathlib import Path
from typing import Dict

from app.controllers.base import ExtractionResult
from app.engine import llm_client
from app.engine.bioresonance_parser import (
    parse_bioresonance_pdf,
    to_deterministic_dict as biores_to_dict,
)
from app.engine.biowell_parser import (
    parse_biowell_chakra_details,
    parse_biowell_functional_table,
)
from app.engine.ecg_parser import (
    parse_ecg_pdf,
    parse_hrv_pdf,
    merge_ecg_hrv,
    to_deterministic_dict as ecg_to_dict,
)
from app.engine.nadi_parser import (
    parse_nadi_text,
    to_deterministic_dict as nadi_to_dict,
)
from app.engine.dmit_parser import (
    parse_dmit_pdf,
    to_deterministic_dict as dmit_to_dict,
)
from app.engine.prompts import DEVICE_PROMPTS, SYNTHESIS_PROMPT, SYSTEM_PROMPT
from app.engine.scoring import compute_scores
from app.engine.interpretation import build_interpretations
from app.engine.summary_generator import generate_all_summaries
from app.engine.food_knowledge import (
    apply_recommendations_to_wellness,
    generate_recommendations,
)

log = logging.getLogger(__name__)

# Max chars to send per device to LLM
MAX_TEXT_PER_DEVICE = 4000


async def synthesize_report(
    extractions: Dict[str, ExtractionResult],
    report_dir: str | None = None,
    biores_pdf_path: str | None = None,
    ecg_pdf_path: str | None = None,
    hrv_pdf_path: str | None = None,
    dmit_pdf_path: str | None = None,
    biowell_pdf_path: str | None = None,
) -> dict:
    """Run the full pipeline with deterministic Bioresonance/ECG/HRV/Nadi scoring.

    Args:
        extractions:      Mapping of device_key → ExtractionResult.
        report_dir:       Directory to cache intermediate results.
        biores_pdf_path:  Path to the Bioresonance PDF for direct parsing.
        ecg_pdf_path:     Path to the ECG PDF for direct parsing.
        hrv_pdf_path:     Path to the HRV PDF for direct parsing.
        dmit_pdf_path:    Path to the DMIT PDF for direct parsing.
        biowell_pdf_path: Path to the BioWell PDF for biorhythm graph extraction.

    Returns:
        Validated wellness report dict with deterministic scores.
    """
    total_start = time.time()
    cache_dir = Path(report_dir) / "cache" if report_dir else None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Parse devices directly (NO LLM) ──────────────────────
    biores_data = None
    ecg_data = None
    nadi_data = None
    dmit_data = None
    biowell_functional_data = None

    # 1a) Bioresonance
    if biores_pdf_path:
        log.info("Step 1a: Parsing Bioresonance PDF directly (no LLM)...")
        biores_result = parse_bioresonance_pdf(biores_pdf_path)
        biores_data = biores_to_dict(biores_result)
        log.info(
            f"  Parsed {biores_data['total_organs_scanned']} organs, "
            f"system scores: {biores_data['system_scores']}"
        )
        if cache_dir:
            (cache_dir / "biores_parsed.json").write_text(
                json.dumps(biores_data, indent=2), encoding="utf-8"
            )
    elif cache_dir and (cache_dir / "biores_parsed.json").exists():
        log.info("Step 1a: Using cached Bioresonance parse")
        biores_data = json.loads(
            (cache_dir / "biores_parsed.json").read_text(encoding="utf-8")
        )

    # 1b) ECG + HRV
    if ecg_pdf_path or hrv_pdf_path:
        log.info("Step 1b: Parsing ECG/HRV PDFs directly (no LLM)...")
        ecg_result = parse_ecg_pdf(ecg_pdf_path) if ecg_pdf_path else None
        hrv_result = parse_hrv_pdf(hrv_pdf_path) if hrv_pdf_path else None

        if ecg_result and hrv_result:
            merged = merge_ecg_hrv(ecg_result, hrv_result)
        else:
            merged = ecg_result or hrv_result

        ecg_data = ecg_to_dict(merged)
        log.info(
            f"  ECG: HR={ecg_data['ecg']['heart_rate_bpm']}, "
            f"QTc={ecg_data['ecg']['qtc_interval_ms']}, "
            f"LF/HF={ecg_data['hrv']['lf_hf_ratio']}"
        )
        if cache_dir:
            (cache_dir / "ecg_parsed.json").write_text(
                json.dumps(ecg_data, indent=2), encoding="utf-8"
            )
    elif cache_dir and (cache_dir / "ecg_parsed.json").exists():
        log.info("Step 1b: Using cached ECG parse")
        ecg_data = json.loads(
            (cache_dir / "ecg_parsed.json").read_text(encoding="utf-8")
        )

    # 1c) Nadi — parse from OCR text already extracted
    nadi_ext = extractions.get("nadi")
    if nadi_ext and nadi_ext.raw_text and nadi_ext.raw_text.strip():
        log.info("Step 1c: Parsing Nadi OCR text directly (no LLM)...")
        nadi_result = parse_nadi_text(nadi_ext.raw_text)
        nadi_data = nadi_to_dict(nadi_result)
        log.info(
            f"  Nadi: pulse={nadi_data['pulse']['rate_bpm']}, "
            f"prakriti={nadi_data['dosha']['prakriti']}, "
            f"params={len(nadi_data['health_params'])}"
        )
        if cache_dir:
            (cache_dir / "nadi_parsed.json").write_text(
                json.dumps(nadi_data, indent=2), encoding="utf-8"
            )
    elif cache_dir and (cache_dir / "nadi_parsed.json").exists():
        log.info("Step 1c: Using cached Nadi parse")
        nadi_data = json.loads(
            (cache_dir / "nadi_parsed.json").read_text(encoding="utf-8")
        )

    # 1d) DMIT
    if dmit_pdf_path:
        log.info("Step 1d: Parsing DMIT PDF directly (no LLM)...")
        dmit_result = parse_dmit_pdf(dmit_pdf_path)
        dmit_data = dmit_to_dict(dmit_result)
        log.info(
            f"  DMIT: L={dmit_data['brain_dominance']['left_pct']}% "
            f"R={dmit_data['brain_dominance']['right_pct']}% "
            f"TFRC={dmit_data['tfrc']['total']} "
            f"personality={dmit_data['personality']['primary']}"
        )
        if cache_dir:
            (cache_dir / "dmit_parsed.json").write_text(
                json.dumps(dmit_data, indent=2), encoding="utf-8"
            )
    elif cache_dir and (cache_dir / "dmit_parsed.json").exists():
        log.info("Step 1d: Using cached DMIT parse")
        dmit_data = json.loads(
            (cache_dir / "dmit_parsed.json").read_text(encoding="utf-8")
        )

    # ── Step 1e: Extract Biorhythm graph image from BioWell PDF ──────
    biorhythm_image_path = None
    if biowell_pdf_path:
        log.info("Step 1e: Extracting biorhythm graph from BioWell PDF...")
        out_path = str(Path(report_dir) / "biorhythm_graph.png") if report_dir else None
        biorhythm_image_path = extract_biorhythm_image(biowell_pdf_path, out_path)
        if biorhythm_image_path:
            log.info(f"  Biorhythm graph saved: {biorhythm_image_path}")
        else:
            log.warning("  Could not extract biorhythm graph")
    elif report_dir and (Path(report_dir) / "biorhythm_graph.png").exists():
        biorhythm_image_path = str(Path(report_dir) / "biorhythm_graph.png")
        log.info("Step 1e: Using cached biorhythm graph")

    # ── Step 2: Cache raw extracted text ─────────────────────────────
    log.info("Step 2: Caching raw extracted text...")
    for key, ext in extractions.items():
        if cache_dir and ext and ext.raw_text:
            (cache_dir / f"{key}_raw.txt").write_text(
                ext.raw_text[:50000], encoding="utf-8"
            )
            log.info(
                f"  {key}: {len(ext.raw_text)} chars, "
                f"{ext.page_count} pages"
            )

    # ── Step 2b: Parse BioWell functional table deterministically ────
    biowell_raw = ""
    biowell_ext = extractions.get("biowell")
    if biowell_ext and biowell_ext.raw_text:
        biowell_raw = biowell_ext.raw_text
    elif cache_dir and (cache_dir / "biowell_raw.txt").exists():
        biowell_raw = (cache_dir / "biowell_raw.txt").read_text(encoding="utf-8")

    biowell_chakra_data = {"chakra_details": {}}
    if biowell_raw:
        biowell_functional_data = parse_biowell_functional_table(biowell_raw)
        row_count = len(biowell_functional_data.get("organ_energy_levels", []))
        log.info(f"Step 2b: Parsed BioWell functional table rows={row_count}")
        biowell_chakra_data = parse_biowell_chakra_details(biowell_raw)
        chakra_count = len(biowell_chakra_data.get("chakra_details", {}))
        log.info(f"Step 2c: Parsed BioWell chakra rows={chakra_count}")
        if cache_dir:
            (cache_dir / "biowell_functional_parsed.json").write_text(
                json.dumps(biowell_functional_data, indent=2), encoding="utf-8"
            )
            (cache_dir / "biowell_chakra_parsed.json").write_text(
                json.dumps(biowell_chakra_data, indent=2), encoding="utf-8"
            )
    elif cache_dir and (cache_dir / "biowell_functional_parsed.json").exists():
        biowell_functional_data = json.loads(
            (cache_dir / "biowell_functional_parsed.json").read_text(encoding="utf-8")
        )
        if (cache_dir / "biowell_chakra_parsed.json").exists():
            biowell_chakra_data = json.loads(
                (cache_dir / "biowell_chakra_parsed.json").read_text(encoding="utf-8")
            )

    # ── Step 3: Compress text for each device ────────────────────────
    log.info("Step 3: Compressing text for LLM...")
    compressed: Dict[str, str] = {}
    for key, ext in extractions.items():
        if not ext or ext.error or not ext.raw_text.strip():
            compressed[key] = ""
            continue
        compressed[key] = _compress_text(ext.raw_text, MAX_TEXT_PER_DEVICE)
        log.info(
            f"  {key}: {len(ext.raw_text)} -> {len(compressed[key])} chars"
        )
        if cache_dir:
            (cache_dir / f"{key}_compressed.txt").write_text(
                compressed[key], encoding="utf-8"
            )

    # ── Step 4: LLM extraction — ONLY for devices not parsed above ────
    # Deterministic devices: biores, ecg, hrv, nadi (parsed in Step 1)
    # LLM devices: inbody, biowell
    devices_for_llm = ["inbody", "biowell"]
    if not biores_data:
        devices_for_llm.append("biores")

    parsed_devices = []
    if biores_data:
        parsed_devices.append("biores")
    if ecg_data:
        parsed_devices.append("ecg+hrv")
    if nadi_data:
        parsed_devices.append("nadi")

    log.info(
        f"Step 4: LLM extraction for {devices_for_llm} "
        f"(deterministic: {parsed_devices})..."
    )
    device_summaries: Dict[str, str] = {}

    # Inject parsed data as device summaries
    if biores_data:
        device_summaries["biores"] = json.dumps(biores_data, indent=2)
    if ecg_data:
        device_summaries["ecg"] = json.dumps(ecg_data, indent=2)
    if nadi_data:
        device_summaries["nadi"] = json.dumps(nadi_data, indent=2)

    # Build LLM tasks (skip cached/empty devices)
    async def _extract_one(device_key: str) -> tuple[str, str]:
        """Run a single LLM extraction and return (key, result_json)."""
        text = compressed.get(device_key, "")

        # Check cache first
        if cache_dir:
            cache_file = cache_dir / f"{device_key}_llm.json"
            if cache_file.exists():
                log.info(f"  {device_key}: Using cached LLM result")
                return device_key, cache_file.read_text(encoding="utf-8")

        if not text.strip():
            log.warning(f"  {device_key}: No text — skipping")
            return device_key, json.dumps(
                {"error": f"No data from {device_key}"}
            )

        step_start = time.time()
        log.info(f"  {device_key}: Sending {len(text)} chars to LLM...")

        prompt_template = DEVICE_PROMPTS[device_key]
        prompt = prompt_template.replace("{text}", text)

        try:
            result = await llm_client.generate(
                prompt=prompt,
                system=SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=2048,
                timeout=180.0,
            )
            result_json = json.dumps(result, indent=2)
            elapsed = time.time() - step_start
            log.info(f"  {device_key}: Done in {elapsed:.1f}s")

            if cache_dir:
                (cache_dir / f"{device_key}_llm.json").write_text(
                    result_json, encoding="utf-8"
                )
            return device_key, result_json
        except Exception as e:
            log.error(f"  {device_key}: FAILED — {type(e).__name__}: {e}")
            return device_key, json.dumps(
                {"error": f"LLM failed: {str(e)[:200]}"}
            )

    # Run all LLM extractions in parallel
    step4_start = time.time()
    tasks = [_extract_one(dk) for dk in devices_for_llm]
    results = await asyncio.gather(*tasks)
    for dk, result_json in results:
        device_summaries[dk] = result_json

    inbody_raw = _device_raw_text(extractions, cache_dir, "inbody")
    if inbody_raw and device_summaries.get("inbody"):
        try:
            inbody_summary = json.loads(device_summaries["inbody"])
            deterministic_inbody = _parse_inbody_ocr_text(inbody_raw)
            if deterministic_inbody:
                inbody_summary.update({
                    key: value
                    for key, value in deterministic_inbody.items()
                    if value not in (None, 0, 0.0, "")
                })
                device_summaries["inbody"] = json.dumps(inbody_summary, indent=2)
                if cache_dir:
                    (cache_dir / "inbody_llm.json").write_text(
                        device_summaries["inbody"], encoding="utf-8"
                    )
                log.info(
                    "  inbody: Applied deterministic OCR corrections "
                    f"{deterministic_inbody}"
                )
        except Exception as e:
            log.warning(f"  inbody: deterministic OCR correction skipped: {e}")
    log.info(
        f"Step 4: All LLM extractions done in {time.time() - step4_start:.1f}s"
    )

    # ── Step 5: Synthesis — inject deterministic scores ───────────────
    log.info("Step 5: Synthesizing unified report...")
    step5_start = time.time()

    # Build the synthesis prompt with bioresonance scores injected
    biores_context = device_summaries.get("biores", "{}")
    if biores_data:
        # Inject deterministic system scores so LLM MUST use them
        biores_context = json.dumps({
            "parsed_system_scores": biores_data["system_scores"],
            "hormone_levels": biores_data.get("hormone_levels", {}),
            "organs_needing_attention": biores_data.get("summary", {}).get(
                "organs_needing_attention", []
            ),
            "total_organs_scanned": biores_data.get("total_organs_scanned", 0),
            "instruction": (
                "USE THESE EXACT SCORES for body systems. "
                "Do NOT change or reinterpret them."
            ),
        }, indent=2)

    synthesis_prompt = SYNTHESIS_PROMPT.format(
        ecg_summary=device_summaries.get("ecg", "{}"),
        nadi_summary=device_summaries.get("nadi", "{}"),
        inbody_summary=device_summaries.get("inbody", "{}"),
        biowell_summary=device_summaries.get("biowell", "{}"),
        biores_summary=biores_context,
    )

    try:
        report = await llm_client.generate(
            prompt=synthesis_prompt,
            system=SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=4096,
            timeout=300.0,
        )
        step5_time = time.time() - step5_start
        total_time = time.time() - total_start
        log.info(
            f"Step 5: Done in {step5_time:.1f}s | "
            f"Total: {total_time:.1f}s"
        )

        # Validate, fill defaults, then apply deterministic scoring
        validated = _validate_and_fill(report)

        # Inject patient info from parsed devices
        patient = validated.get("patient", {})
        for src_data in [biores_data, ecg_data, nadi_data]:
            if src_data:
                sp = src_data.get("patient", {})
                if not patient.get("name") or patient["name"] == "Unknown":
                    patient["name"] = sp.get("name", "")
                if not patient.get("age"):
                    patient["age"] = sp.get("age", "")
                if not patient.get("date"):
                    patient["date"] = sp.get("date", "")

        # Inject ECG/HRV metrics
        metrics = validated.get("metrics", {})
        inbody_data = {}
        try:
            inbody_data = json.loads(device_summaries.get("inbody", "{}"))
        except Exception:
            inbody_data = {}
        if inbody_data:
            _inject_metric(metrics, "weight", inbody_data.get("weight_kg"))
            _inject_metric(metrics, "visceralFat", inbody_data.get("visceral_fat_level"))
            _inject_metric(metrics, "bmi", inbody_data.get("bmi"))
            _inject_metric(metrics, "bodyFat", inbody_data.get("body_fat_mass_kg"))

        if ecg_data:
            ecg_vals = ecg_data.get("ecg", {})
            if ecg_vals.get("heart_rate_bpm") and not metrics.get("heartRate"):
                metrics["heartRate"] = ecg_vals["heart_rate_bpm"]
            hrv_vals = ecg_data.get("hrv", {})
            if hrv_vals.get("lf_hf_ratio") and not metrics.get("lfhfRatio"):
                metrics["lfhfRatio"] = hrv_vals["lf_hf_ratio"]

        # Inject Nadi pulse
        if nadi_data:
            pulse = nadi_data.get("pulse", {}).get("rate_bpm", 0)
            if pulse and not metrics.get("nadiPulse"):
                metrics["nadiPulse"] = pulse

        # Inject BioWell metrics — regex fallback when LLM returns null
        if not metrics.get("bioEnergy") or metrics["bioEnergy"] == 0:
            biowell_raw = ""
            biowell_ext = extractions.get("biowell")
            if biowell_ext and biowell_ext.raw_text:
                biowell_raw = biowell_ext.raw_text
            elif cache_dir and (cache_dir / "biowell_raw.txt").exists():
                biowell_raw = (cache_dir / "biowell_raw.txt").read_text(
                    encoding="utf-8"
                )
            if biowell_raw:
                # "Energy 62 Joules (x10-2)"
                m = re.search(
                    r"Energy\s+(\d+\.?\d*)\s*Joules", biowell_raw
                )
                if m:
                    metrics["bioEnergy"] = float(m.group(1))
                    log.info(
                        f"  BioWell bioEnergy={metrics['bioEnergy']} "
                        f"(regex fallback)"
                    )
                # "Energy reserve 100%"
                m = re.search(
                    r"Energy\s+reserve\s+(\d+)%", biowell_raw
                )
                if m:
                    metrics["energyReserve"] = int(m.group(1))
                    log.info(
                        f"  BioWell energyReserve={metrics['energyReserve']}% "
                        f"(regex fallback)"
                    )

        # Inject Nadi wellness recommendations
        if nadi_data:
            nadi_wellness = nadi_data.get("wellness", {})
            report_wellness = validated.get("wellness", {})
            if nadi_wellness.get("diet_eat"):
                eat = ", ".join(nadi_wellness["diet_eat"])
                diet_text = f"Recommended: {eat}."
                avoid_items = nadi_wellness.get("diet_avoid", [])
                if avoid_items:
                    diet_text += f" Avoid: {', '.join(avoid_items)}."
                report_wellness["diet"] = diet_text
            if nadi_wellness.get("yoga"):
                report_wellness["yoga"] = ", ".join(nadi_wellness["yoga"])
            if nadi_wellness.get("exercise"):
                report_wellness["physicalActivity"] = (
                    ", ".join(nadi_wellness["exercise"])
                )
            if nadi_wellness.get("supplements"):
                report_wellness["supplements"] = (
                    ", ".join(nadi_wellness["supplements"])
                )
            if nadi_wellness.get("medicines"):
                report_wellness["medicine"] = (
                    ", ".join(nadi_wellness["medicines"])
                )

        # Load BioWell LLM data for scoring
        biowell_data = None
        if cache_dir and (cache_dir / "biowell_llm.json").exists():
            try:
                biowell_data = json.loads(
                    (cache_dir / "biowell_llm.json").read_text(encoding="utf-8")
                )
                log.info("Loaded BioWell LLM data for system scoring")
            except Exception:
                pass
        if biowell_functional_data and biowell_functional_data.get("organ_energy_levels"):
            biowell_data = biowell_data or {}
            biowell_data["organ_energy_levels"] = biowell_functional_data.get(
                "organ_energy_levels", []
            )
            log.info("Using deterministic BioWell Balance% rows for system scoring")
        if biowell_chakra_data.get("chakra_details"):
            biowell_data = biowell_data or {}
            biowell_data["chakra_details"] = biowell_chakra_data.get(
                "chakra_details", {}
            )
            log.info("Using deterministic BioWell chakra details for Page 1 summaries")

        scored = compute_scores(
            validated,
            biores_data=biores_data,
            ecg_data=ecg_data,
            nadi_data=nadi_data,
            biowell_data=biowell_data,
        )

        # Step 6: Inject deterministic interpretations from doctor's rules
        log.info("Step 6: Applying deterministic interpretations (summary_requirement.docx)...")
        final = build_interpretations(
            scored,
            biores_data=biores_data,
            ecg_data=ecg_data,
            nadi_data=nadi_data,
            biowell_data=biowell_data,
        )
        log.info("Step 6: Done — all dimension descriptions are now deterministic")

        # Step 7: Generate AI summaries (uses OLLAMA_SUMMARY_MODEL)
        log.info("Step 7: Generating AI clinical summaries...")
        try:
            summaries = await generate_all_summaries(
                final,
                nadi_data=nadi_data,
                ecg_data=ecg_data,
                biowell_data=biowell_data,
                biores_data=biores_data,
                dmit_data=dmit_data,
            )

            # Override dimension descriptions with AI summaries
            dim_summaries = summaries.get("dimension_summaries", {})
            for dim_key in ["physical", "psychological", "emotional", "spiritual"]:
                ai_text = dim_summaries.get(dim_key, "")
                if ai_text and not ai_text.startswith("Summary generation"):
                    final.setdefault("dimensions", {}).setdefault(dim_key, {})
                    final["dimensions"][dim_key]["description"] = ai_text

            # Inject system summaries
            sys_summaries = summaries.get("system_summaries", {})
            final["system_summaries"] = sys_summaries

            # Inject SWOT
            final["swot"] = summaries.get("swot", {})

            log.info("Step 7: Done — AI summaries injected")
        except Exception as e:
            log.warning(f"Step 7: AI summary generation failed (non-fatal): {e}")
            # Non-fatal — deterministic descriptions from Step 6 remain

        # Step 8: Inject DMIT data
        if dmit_data:
            final["dmit"] = dmit_data
            log.info("Step 8: DMIT data injected")

        # Step 8b: Inject biorhythm graph path
        if biorhythm_image_path:
            final["biorhythm"] = {"image_path": biorhythm_image_path}
            log.info(f"Step 8b: Biorhythm graph injected: {biorhythm_image_path}")

        # Step 8c: Compute biorhythm day-by-day calendar interpretation
        patient_data = final.get("patient", {})
        calendar_data = build_biorhythm_calendar(patient_data, biowell_raw)
        if calendar_data:
            final.setdefault("biorhythm", {})["calendar"] = calendar_data
            log.info(
                f"Step 8c: Biorhythm calendar computed — "
                f"{calendar_data['month_name']}, {len(calendar_data['days'])} days, "
                f"{len(calendar_data['watch_days'])} watch days"
            )
        else:
            log.warning("Step 8c: Biorhythm calendar skipped — no DOB/age available")

        # Step 9: Generate food & supplement recommendations (deterministic)
        log.info("Step 9: Generating food & supplement recommendations...")
        try:
            food_recs = generate_recommendations(
                systems=final.get("systems", {}),
                metrics=final.get("metrics", {}),
                nadi_data=nadi_data,
                dimensions=final.get("dimensions", {}),
            )
            final["food_recommendations"] = food_recs
            final["wellness"] = apply_recommendations_to_wellness(
                final.get("wellness", {}),
                food_recs,
                nadi_data=nadi_data,
            )
            log.info(
                f"Step 9: Done — {len(food_recs.get('priority_systems', []))} priority systems, "
                f"{len(food_recs.get('medicines', []))} medicines, "
                f"{len(food_recs.get('functional_foods', []))} foods"
            )
        except Exception as e:
            log.warning(f"Step 9: Food recommendations failed (non-fatal): {e}")
            final["food_recommendations"] = {}

        # Cache final summaries
        if cache_dir:
            (cache_dir / "ai_summaries.json").write_text(
                json.dumps(summaries if 'summaries' in dir() else {}, indent=2),
                encoding="utf-8",
            )

        total_time = time.time() - total_start
        log.info(f"Pipeline complete in {total_time:.1f}s")
        return final
    except Exception as e:
        log.error(f"Step 5: Synthesis FAILED — {e}")
        raise ValueError(f"Report synthesis failed: {e}") from e


def _compress_text(raw: str, max_chars: int) -> str:
    """Compress extracted text to fit within max_chars."""
    if len(raw) <= max_chars:
        return raw
    head = int(max_chars * 0.6)
    tail = max_chars - head
    return raw[:head] + "\n\n[... content trimmed ...]\n\n" + raw[-tail:]


def _device_raw_text(
    extractions: Dict[str, ExtractionResult],
    cache_dir: Path | None,
    device_key: str,
) -> str:
    """Return raw extracted text from current extraction or cache."""
    ext = extractions.get(device_key)
    if ext and ext.raw_text:
        return ext.raw_text
    if cache_dir and (cache_dir / f"{device_key}_raw.txt").exists():
        return (cache_dir / f"{device_key}_raw.txt").read_text(encoding="utf-8")
    return ""


def _to_number(value):
    """Convert simple numeric OCR/LLM values to int/float."""
    if value in (None, ""):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _inject_metric(metrics: dict, key: str, value):
    """Inject a metric when a deterministic parsed value is available."""
    number = _to_number(value)
    if number is not None:
        metrics[key] = number


def _parse_inbody_ocr_text(raw_text: str) -> dict:
    """Extract InBody metrics deterministically from OCR text.

    InBody screenshots often put the overall score beside the visceral section:
    "Visceral Fat Level 61Points" followed by "12". The Lv value is 12, while
    61 is the InBody score, so the parser deliberately prefers the number after
    a "Points" token.
    """
    text = re.sub(r"[ \t]+", " ", str(raw_text or ""))
    parsed = {}

    patterns = {
        "weight_kg": r"Weight\s+(?:InBody\s+)?(\d+(?:\.\d+)?)\s*kg",
        "skeletal_muscle_mass_kg": r"Skeletal\s+Muscle\s+Mass\s+(\d+(?:\.\d+)?)",
        "body_fat_mass_kg": r"Body\s+Fat\s+Mass\s+(\d+(?:\.\d+)?)",
        "bmi": r"\bBMI\s+(\d+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            parsed[key] = _to_number(match.group(1))

    visceral_match = re.search(
        r"Visceral\s+Fat\s+Level(?P<section>.*?)(?:Top\b|Low\b|High\b|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if visceral_match:
        section = visceral_match.group("section")
        lv_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:Lv|LV)\b", section)
        if lv_match:
            parsed["visceral_fat_level"] = _to_number(lv_match.group(1))
        else:
            numbers = re.findall(r"\d+(?:\.\d+)?", section)
            points_first = re.match(r"\s*\d+(?:\.\d+)?\s*Points?\b", section, re.IGNORECASE)
            if points_first and len(numbers) >= 2:
                parsed["visceral_fat_level"] = _to_number(numbers[1])
            elif numbers:
                parsed["visceral_fat_level"] = _to_number(numbers[0])

    score_match = re.search(r"\b(\d+(?:\.\d+)?)\s*Points\b", text, flags=re.IGNORECASE)
    if score_match:
        parsed["inbody_score_points"] = _to_number(score_match.group(1))

    return parsed


def _validate_and_fill(report: dict) -> dict:
    """Ensure all required keys exist with sensible defaults."""
    defaults = {
        "patient": {"name": "Unknown", "age": "", "date": ""},
        "metrics": {
            "weight": 0.0, "visceralFat": 0.0, "bmi": 0.0, "bodyFat": 0.0,
            "heartRate": 0, "bioEnergy": 0.0, "energyReserve": 0,
            "lfhfRatio": 0.0, "nadiPulse": 0,
        },
        "dimensions": {
            dim: {"score": 50, "description": "Data unavailable"}
            for dim in ["physical", "emotional", "psychological", "spiritual"]
        },
        "systems": {
            sys: {"score": 50, "status": "Need Attention"}
            for sys in [
                "nervous", "cardiovascular", "respiratory",
                "musculoskeletal", "digestive", "integumentary",
                "endocrine", "urogenital", "reproductive", "immune",
            ]
        },
        "wellness": {
            key: "No recommendation available"
            for key in [
                "diet", "yoga", "physicalActivity", "sleep",
                "stress", "supplements", "medicine",
            ]
        },
    }

    for section, section_defaults in defaults.items():
        if section not in report or report[section] is None:
            report[section] = section_defaults
        elif isinstance(section_defaults, dict):
            for key, default_val in section_defaults.items():
                current = report[section].get(key)
                if current is None or key not in report[section]:
                    report[section][key] = default_val
                elif isinstance(default_val, dict) and isinstance(current, dict):
                    for sub_key, sub_val in default_val.items():
                        if sub_key not in current or current[sub_key] is None:
                            current[sub_key] = sub_val

    # Clean placeholder text from patient fields
    patient = report.get("patient", {})
    for field_name in ["name", "age", "date"]:
        val = patient.get(field_name, "")
        if val and any(p in str(val).lower() for p in [
            "not provided", "not specified", "report date",
            "patient name", "age string", "unknown",
        ]):
            patient[field_name] = ""

    # Flatten wellness arrays to strings
    wellness = report.get("wellness", {})
    for key in ["diet", "yoga", "physicalActivity", "sleep",
                 "stress", "supplements", "medicine"]:
        val = wellness.get(key)
        if isinstance(val, list):
            parts = []
            for item in val:
                if isinstance(item, dict):
                    name = item.get("name", "")
                    desc = item.get("description", "")
                    parts.append(f"{name}: {desc}" if name else desc)
                elif isinstance(item, str):
                    parts.append(item)
            wellness[key] = ". ".join(parts) if parts else "No recommendation available"
        elif val is None:
            wellness[key] = "No recommendation available"

    return report
