"""Prompt templates for device-specific extraction and final synthesis."""

# ─────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT (shared across all LLM calls)
# ─────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a medical data extraction and wellness report AI. "
    "You ONLY output valid JSON — no markdown, no commentary, no backticks. "
    "Extract information precisely from the text provided."
)

# ─────────────────────────────────────────────────────────────────────
# STEP 1 — Per-device extraction prompts
# Each takes the raw extracted text and returns a focused JSON summary.
# ─────────────────────────────────────────────────────────────────────

ECG_EXTRACT_PROMPT = """Analyze the following ECG / HRV report text and extract key values.

--- BEGIN ECG REPORT ---
{text}
--- END ECG REPORT ---

Return ONLY this JSON structure (use null for missing values):
{{
  "heart_rate_bpm": 0,
  "rhythm": "Normal Sinus / Abnormal / etc",
  "hrv": {{
    "sdnn_ms": 0.0,
    "rmssd_ms": 0.0,
    "lf_power": 0.0,
    "hf_power": 0.0,
    "lf_hf_ratio": 0.0,
    "stress_index": 0.0
  }},
  "abnormalities": ["list of flagged conditions"],
  "overall_impression": "1-2 sentence summary"
}}"""

NADI_EXTRACT_PROMPT = """Analyze the following Nadi Tarangini (Ayurvedic Pulse Diagnostic) report text.
This is the PRIMARY source for wellness recommendations.

--- BEGIN NADI TARANGINI REPORT ---
{text}
--- END NADI TARANGINI REPORT ---

Return ONLY this JSON structure (use null for missing values):
{{
  "pulse_rate_bpm": 0,
  "prakriti": "Vata/Pitta/Kapha constitution",
  "vikruti": "Current imbalance description",
  "dosha_analysis": {{
    "vata": {{"score": 0, "status": "Normal/Elevated/Low"}},
    "pitta": {{"score": 0, "status": "Normal/Elevated/Low"}},
    "kapha": {{"score": 0, "status": "Normal/Elevated/Low"}}
  }},
  "organ_health": {{
    "nervous_system": "status and notes",
    "cardiovascular": "status and notes",
    "respiratory": "status and notes",
    "digestive": "status and notes",
    "musculoskeletal": "status and notes",
    "integumentary": "status and notes",
    "endocrine": "status and notes",
    "urogenital": "status and notes",
    "reproductive": "status and notes",
    "immune": "status and notes"
  }},
  "recommendations": {{
    "diet": "dietary recommendations in detail",
    "yoga": "yoga therapy recommendations",
    "physical_activity": "exercise and activity guidance",
    "sleep": "sleep-related guidance",
    "stress": "stress management techniques",
    "supplements": "recommended supplements",
    "medicine": "ayurvedic medicines / herbs prescribed"
  }},
  "overall_summary": "2-3 sentence overall assessment"
}}"""

INBODY_EXTRACT_PROMPT = """Analyze the following InBody body composition data (extracted via OCR from an image).
Some values may be partially readable — extract what you can.
Important: "Visceral Fat Level" is the Lv value. Do not confuse it with the InBody score shown as "Points" on the right side.
Example: if OCR says "Visceral Fat Level 61Points" followed by "12", return visceral_fat_level = 12 and not 61.

--- BEGIN INBODY DATA ---
{text}
--- END INBODY DATA ---

Return ONLY this JSON structure (use null for missing values):
{{
  "weight_kg": 0.0,
  "skeletal_muscle_mass_kg": 0.0,
  "body_fat_mass_kg": 0.0,
  "bmi": 0.0,
  "body_fat_percentage": 0.0,
  "visceral_fat_level": 0,
  "basal_metabolic_rate_kcal": 0,
  "total_body_water_l": 0.0,
  "overall_assessment": "1-2 sentence body composition summary"
}}"""

BIOWELL_EXTRACT_PROMPT = """Analyze the following Bio-Well (GDV / Gas Discharge Visualization) report text.
Bio-Well measures energy fields, stress, and chakra alignment.

--- BEGIN BIO-WELL REPORT ---
{text}
--- END BIO-WELL REPORT ---

Return ONLY this JSON structure (use null for missing values):
{{
  "overall_energy_joules": 0.0,
  "energy_reserve_percent": 0,
  "stress_index": 0.0,
  "stress_level": "Low/Moderate/High",
  "chakra_alignment": {{
    "root": {{"energy": 0, "alignment": "Good/Moderate/Poor"}},
    "sacral": {{"energy": 0, "alignment": "Good/Moderate/Poor"}},
    "solar_plexus": {{"energy": 0, "alignment": "Good/Moderate/Poor"}},
    "heart": {{"energy": 0, "alignment": "Good/Moderate/Poor"}},
    "throat": {{"energy": 0, "alignment": "Good/Moderate/Poor"}},
    "third_eye": {{"energy": 0, "alignment": "Good/Moderate/Poor"}},
    "crown": {{"energy": 0, "alignment": "Good/Moderate/Poor"}}
  }},
  "organ_energy_levels": [
    {{
      "system_group": "system heading from the table, e.g. Cardiovascular system",
      "organ": "organ or system name exactly as shown in the Functional/energetic table",
      "energy_joules": 0.0,
      "balance_percent": 0.0,
      "status": "Low/Optimal/Increased/Heightened if stated"
    }}
  ],
  "emotional_psychological": "summary of emotional/psychological indicators",
  "overall_impression": "1-2 sentence summary"
}}"""

BIORESONANCE_EXTRACT_PROMPT = """Analyze the following Bioresonance (Frequency Scan) report text.
Bioresonance measures electromagnetic signals from the body via electrodes.

--- BEGIN BIORESONANCE REPORT ---
{text}
--- END BIORESONANCE REPORT ---

Return ONLY this JSON structure (use null for missing values):
{{
  "scan_summary": "overall scan findings",
  "organ_stress_levels": {{
    "organ_name": {{"stress_level": "Low/Moderate/High", "notes": "details"}}
  }},
  "system_findings": {{
    "nervous": "findings",
    "cardiovascular": "findings",
    "respiratory": "findings",
    "digestive": "findings",
    "musculoskeletal": "findings",
    "integumentary": "findings",
    "endocrine": "findings",
    "urogenital": "findings",
    "reproductive": "findings",
    "immune": "findings"
  }},
  "frequency_imbalances": ["list of notable frequency imbalances"],
  "overall_impression": "1-2 sentence summary"
}}"""

# Mapping device key → extraction prompt
DEVICE_PROMPTS = {
    "ecg": ECG_EXTRACT_PROMPT,
    "nadi": NADI_EXTRACT_PROMPT,
    "inbody": INBODY_EXTRACT_PROMPT,
    "biowell": BIOWELL_EXTRACT_PROMPT,
    "biores": BIORESONANCE_EXTRACT_PROMPT,
}

# ─────────────────────────────────────────────────────────────────────
# STEP 2 — Final synthesis prompt
# Takes all 5 device summaries and produces the unified report.
# ─────────────────────────────────────────────────────────────────────

SYNTHESIS_PROMPT = """You are a medical wellness report synthesizer for Kadamba Wellness / Nanocare.
You have received structured summaries from 5 medical devices. Your task is to synthesize
them into a single unified wellness report.

=== DEVICE SUMMARIES ===

**ECG / HRV Analysis:**
{ecg_summary}

**Nadi Tarangini (Ayurvedic Pulse Diagnosis):**
{nadi_summary}

**InBody (Body Composition):**
{inbody_summary}

**Bio-Well (GDV Energy Analysis):**
{biowell_summary}

**Bioresonance (Frequency Scan):**
{biores_summary}

=== SYNTHESIS RULES ===

1. Nadi Tarangini is the PRIMARY SOURCE for diet, yoga, supplements, medicine, and lifestyle recommendations.
   When devices conflict on recommendations, Nadi Tarangini wins.

2. CRITICAL — SCORING (scores MUST be between 1 and 100, NEVER 0):
   - Score 80-100 → status "Normal" (healthy, no concerns)
   - Score 60-79  → status "Normal" (acceptable, minor observations)
   - Score 40-59  → status "Need Attention" (moderate concern)
   - Score 1-39   → status "Need Attention" (significant concern)
   - NEVER output a score of exactly 0. If data is missing, estimate 50.
   - Base scores on actual findings from the device data.

3. Dimension scoring logic:
   - Physical: InBody composition (BMI, body fat%, muscle mass) + ECG normality + Bioresonance physical findings
   - Emotional: Bio-Well stress index + Nadi vikruti/pulse quality + Bioresonance emotional indicators
   - Psychological: Bio-Well psychology indicators + Nadi stress/overthinking parameters
   - Spiritual: Bio-Well chakra alignment % + energy reserve %

4. System scores: synthesize ALL relevant device readings for each body system.
   Cross-reference Nadi organ_health, Bio-Well organ_energy, Bioresonance system_findings.

5. Wellness offerings: Use Nadi Tarangini recommendations as the primary source.
   Supplement with insights from other devices where relevant.
   Each offering MUST contain at least 2-3 sentences of actionable advice.

6. Metrics: Extract ACTUAL numeric values from device summaries.
   - weight, visceralFat, bmi, bodyFat from InBody
   - For InBody, visceralFat means "Visceral Fat Level" in Lv units, NOT the InBody score/points.
   - heartRate from ECG
   - bioEnergy, energyReserve from Bio-Well
   - lfhfRatio from ECG HRV data
   - nadiPulse from Nadi Tarangini

=== REQUIRED OUTPUT (JSON only, no markdown, no backticks) ===

{{
  "patient": {{
    "name": "patient name from any report",
    "age": "age string",
    "date": "report date"
  }},
  "metrics": {{
    "weight": <number from InBody>,
    "visceralFat": <Visceral Fat Level from InBody, Lv number>,
    "bmi": <number from InBody>,
    "bodyFat": <number from InBody>,
    "heartRate": <number from ECG>,
    "bioEnergy": <number from BioWell or 0.0>,
    "energyReserve": <number from BioWell or 0>,
    "lfhfRatio": <number from ECG HRV or 0.0>,
    "nadiPulse": <number from Nadi or 0>
  }},
  "dimensions": {{
    "physical": {{"score": <1-100>, "description": "2-sentence clinical summary based on data"}},
    "emotional": {{"score": <1-100>, "description": "2-sentence clinical summary based on data"}},
    "psychological": {{"score": <1-100>, "description": "2-sentence clinical summary based on data"}},
    "spiritual": {{"score": <1-100>, "description": "2-sentence clinical summary based on data"}}
  }},
  "systems": {{
    "nervous": {{"score": <1-100>, "status": "Normal or Need Attention"}},
    "cardiovascular": {{"score": <1-100>, "status": "Normal or Need Attention"}},
    "respiratory": {{"score": <1-100>, "status": "Normal or Need Attention"}},
    "musculoskeletal": {{"score": <1-100>, "status": "Normal or Need Attention"}},
    "digestive": {{"score": <1-100>, "status": "Normal or Need Attention"}},
    "integumentary": {{"score": <1-100>, "status": "Normal or Need Attention"}},
    "endocrine": {{"score": <1-100>, "status": "Normal or Need Attention"}},
    "urogenital": {{"score": <1-100>, "status": "Normal or Need Attention"}},
    "reproductive": {{"score": <1-100>, "status": "Normal or Need Attention"}},
    "immune": {{"score": <1-100>, "status": "Normal or Need Attention"}}
  }},
  "wellness": {{
    "diet": "detailed dietary recommendations (2-3 sentences minimum)",
    "yoga": "yoga therapy recommendations (2-3 sentences minimum)",
    "physicalActivity": "exercise guidance (2-3 sentences minimum)",
    "sleep": "sleep recommendations (2-3 sentences minimum)",
    "stress": "stress management guidance (2-3 sentences minimum)",
    "supplements": "recommended supplements (2-3 sentences minimum)",
    "medicine": "ayurvedic medicines and herbs (2-3 sentences minimum)"
  }}
}}"""
