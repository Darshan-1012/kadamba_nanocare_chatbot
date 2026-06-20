"""Render Jinja2 template → HTML → PDF via Playwright (headless Chromium).

Usage:
    from app.output.html_renderer import render_pdf
    render_pdf(report_data, output_path="report.pdf")
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path

# pyrefly: ignore [missing-import]
from jinja2 import Environment, FileSystemLoader

log = logging.getLogger(__name__)

# Paths
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "frontend" / "template"
_TEMPLATE_NAME = "report_template.html"
_MAX_CHIP_CHARS = 34
_MAX_BULLET_CHARS = 72


def _build_jinja_env() -> Environment:
    """Create a Jinja2 environment with the template directory."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,  # HTML is pre-authored; no double-escaping
    )
    env.filters["dimension_status"] = _dimension_status
    env.filters["dimension_status_class"] = _dimension_status_class
    env.filters["summary_points"] = _summary_points
    env.filters["system_summary_points"] = _system_summary_points
    env.filters["dmit_personality_label"] = _dmit_personality_label
    env.filters["dmit_phrase"] = _dmit_phrase
    env.globals["metric_indicator"] = _metric_indicator
    env.globals["physical_summary_signal"] = _physical_summary_signal
    env.globals["missing_physical_signal"] = _missing_physical_signal
    env.globals["psychological_summary_signal"] = _psychological_summary_signal
    env.globals["emotional_summary_signal"] = _emotional_summary_signal
    env.globals["emotional_biowell_stress_alias"] = _emotional_biowell_stress_alias
    env.globals["missing_emotional_signal"] = _missing_emotional_signal
    env.globals["spiritual_summary_signal"] = _spiritual_summary_signal
    return env


def _dimension_status(score) -> str:
    """Return a compact score label for Page 1 summary badges."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        value = 0
    if value >= 80:
        return "Good"
    if value >= 60:
        return "Fair"
    if value >= 40:
        return "Needs Attention"
    return "Critical Attention"


def _dimension_status_class(score) -> str:
    """Return the CSS class suffix for a Page 1 score badge."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        value = 0
    if value >= 80:
        return "good"
    if value >= 60:
        return "fair"
    if value >= 40:
        return "attention"
    return "critical"


def _summary_points(value, fallback: str = "", limit: int = 4) -> list[str]:
    """Return structured summary points, falling back to sentence splitting."""
    if isinstance(value, list):
        points = [str(item).strip() for item in value if str(item).strip()]
        return points[:limit]

    text = str(fallback or value or "").strip()
    if not text:
        return []
    chunks = re.split(r"(?<=[.!?])\s+", text)
    points = [chunk.strip() for chunk in chunks if chunk.strip()]
    return points[:limit]


def _system_summary_points(value, limit: int = 2) -> list[str]:
    """Return Page 2 bullets that always surface balance and energy meaning."""
    text = str(value or "").strip()
    if not text:
        return []

    sentences = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+", text) if chunk.strip()]
    preferred: list[str] = []

    for keyword in ("balance", "energy"):
        for sentence in sentences:
            lower = sentence.lower()
            if keyword in lower and sentence not in preferred:
                preferred.append(sentence)
                break

    return preferred[:limit]


def _dmit_personality_label(value) -> str:
    """Convert DMIT bird labels into client-safe personality wording."""
    label = str(value or "").strip().lower()
    return {
        "dove": "Calm",
        "eagle": "Straight forward",
        "peacock": "Expressive",
        "owl": "Analytical",
    }.get(label, str(value or "Not available").strip().title())


def _dmit_phrase(value) -> str:
    """Clean final spacing/case artifacts for display."""
    text = str(value or "").strip()
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_items(text: str, limit: int = 10) -> list[str]:
    """Split compact recommendation text into displayable item chips."""
    text = str(text or "").strip()
    if not text:
        return []
    text = re.sub(r"^[^:]{1,45}:\s*", "", text)
    text = text.rstrip(".")
    parts = re.split(r",|;", text)
    items = [re.sub(r"\s+", " ", part).strip(" .") for part in parts]
    return [_fit_text(item, _MAX_CHIP_CHARS) for item in items if item][:limit]


def _sentence_items(text: str, limit: int = 4) -> list[str]:
    """Split paragraph recommendations into short bullet lines."""
    text = str(text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [_fit_text(part.strip(" ."), _MAX_BULLET_CHARS) for part in parts if part.strip(" .")][:limit]


def _fit_text(text: str, max_chars: int) -> str:
    """Bound display text length so PDF cards do not overflow."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= max_chars:
        return text
    clipped = text[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return f"{clipped}..."


def _extract_labeled_items(text: str, label: str, next_labels: tuple[str, ...] = (), limit: int = 10) -> list[str]:
    """Extract comma-separated items after a label in a wellness sentence."""
    text = str(text or "")
    pattern = re.escape(label) + r"\s*:\s*(.*)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return []
    segment = match.group(1)
    for next_label in next_labels:
        marker = re.search(re.escape(next_label) + r"\s*:", segment, flags=re.IGNORECASE)
        if marker:
            segment = segment[:marker.start()]
    segment = segment.split(".")[0]
    return _split_items(segment, limit=limit)


def _wellness_view(wellness: dict, food_recommendations: dict | None = None) -> dict:
    """Prepare Page 5 display groups from visible wellness and knowledge data."""
    wellness = wellness or {}
    food_recommendations = food_recommendations or {}
    diet_text = wellness.get("diet", "")

    diet = {
        "recommended": _extract_labeled_items(
            diet_text,
            "Recommended foods",
            ("Functional foods", "Avoid or limit"),
            limit=11,
        ),
        "functional": _extract_labeled_items(
            diet_text,
            "Functional foods",
            ("Avoid or limit",),
            limit=6,
        ),
        "avoid": _extract_labeled_items(diet_text, "Avoid or limit", limit=6),
    }
    if not any(diet.values()):
        diet["recommended"] = _split_items(diet_text, limit=12)

    support = {
        "supplements": _split_items(wellness.get("supplements", ""), limit=12),
        "medicine": _split_items(wellness.get("medicine", ""), limit=8),
    }

    return {
        "diet": diet,
        "movement": {
            "yoga": _split_items(wellness.get("yoga", ""), limit=9),
            "activity": _split_items(wellness.get("physicalActivity", ""), limit=8),
        },
        "recovery": {
            "sleep": _sentence_items(wellness.get("sleep", ""), limit=5),
            "stress": _sentence_items(wellness.get("stress", ""), limit=5),
        },
        "support": support,
        "priority_systems": food_recommendations.get("priority_systems", [])[:4],
    }


def _metric_indicator(metric: str, value) -> dict:
    """Return compact Page 1 physical metric indicator data."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0

    def clamp(raw: float) -> float:
        return max(0, min(100, raw))

    if metric == "bmi":
        if numeric < 18.5:
            status, css, note = "Low", "attention", "Below ideal range"
        elif numeric < 25:
            status, css, note = "Normal", "good", "18.5-24.9 target"
        elif numeric < 30:
            status, css, note = "High", "attention", "Above ideal range"
        else:
            status, css, note = "Very high", "critical", "Obesity range"
        return {
            "label": "BMI",
            "value": f"{numeric:.1f}",
            "status": status,
            "class": css,
            "marker": clamp((numeric - 15) / 25 * 100),
            "note": note,
        }

    if metric == "heart_rate":
        if numeric < 60:
            status, css, note = "Low", "attention", "Below 60 bpm"
        elif numeric <= 100:
            status, css, note = "Normal", "good", "60-100 bpm"
        else:
            status, css, note = "High", "critical", "Above 100 bpm"
        return {
            "label": "Heart rate",
            "value": f"{numeric:.0f} bpm",
            "status": status,
            "class": css,
            "marker": clamp((numeric - 45) / 75 * 100),
            "note": note,
        }

    if metric == "lfhf":
        if numeric < 0.8:
            status, css, note = "Low", "attention", "Parasympathetic tilt"
        elif numeric <= 2.5:
            status, css, note = "Balanced", "good", "0.8-2.5 target"
        elif numeric <= 4:
            status, css, note = "Elevated", "attention", "Sympathetic load"
        else:
            status, css, note = "High", "critical", "High stress load"
        return {
            "label": "LF/HF",
            "value": f"{numeric:.2f}",
            "status": status,
            "class": css,
            "marker": clamp(numeric / 5 * 100),
            "note": note,
        }

    if metric == "energy_reserve":
        if numeric >= 80:
            status, css, note = "Optimal", "good", "Strong reserve"
        elif numeric >= 50:
            status, css, note = "Moderate", "attention", "Support recovery"
        else:
            status, css, note = "Low", "critical", "Depleted reserve"
        return {
            "label": "Energy reserve",
            "value": f"{numeric:.0f}%",
            "status": status,
            "class": css,
            "marker": clamp(numeric),
            "note": note,
        }

    return {
        "label": metric.replace("_", " ").title(),
        "value": str(value or "--"),
        "status": "",
        "class": "fair",
        "marker": 0,
        "note": "",
    }


def _physical_summary_signal(point: str) -> dict | None:
    """Parse rule-backed physical summary points into Page 1 signal rows."""
    text = str(point or "").strip()
    if not text:
        return None

    if text.startswith("LF/HF Ratio"):
        return None

    nadi = re.match(r"Nadi\s+(Toxin|Hydration|Flexibility)\s+([0-9.]+)%\s+\(([^)]+)\)\s+--\s+(.+)", text)
    if nadi:
        param = nadi.group(1)
        value = float(nadi.group(2))
        level = nadi.group(3).strip().title()
        note = nadi.group(4).rstrip(".").strip()
    else:
        legacy_nadi = re.match(r"Nadi\s+(Toxin|Hydration|Flexibility)\s+\(([^)]+)\)\s+--\s+(.+)", text)
        if not legacy_nadi:
            return None
        param = legacy_nadi.group(1)
        level = legacy_nadi.group(2).strip().title()
        note = legacy_nadi.group(3).rstrip(".").strip()
        value = {"High": 85.0, "Medium": 60.0, "Low": 25.0}.get(level, 50.0)

    if not param:
        return None

    level_lower = level.lower()

    if param.lower() == "toxin":
        css = "good" if level_lower == "low" else "critical" if level_lower == "high" else "attention"
    else:
        css = "good" if level_lower == "high" else "critical" if level_lower == "low" else "attention"

    return {
        "label": f"{param} level",
        "value": f"{value:g}%",
        "status": level,
        "class": css,
        "marker": max(0, min(100, value)),
        "note": note,
    }


def _missing_physical_signal(param: str) -> dict:
    """Return a visible placeholder for unavailable physical Nadi signals."""
    label = param.strip().title()
    return {
        "label": f"{label} level",
        "value": "--",
        "status": "Not available",
        "class": "attention",
        "marker": 0,
        "note": "Not found in parsed Nadi data",
    }


def _psychological_summary_signal(point: str) -> dict | None:
    """Parse rule-backed psychological summary points into signal rows."""
    text = str(point or "").strip()
    if not text:
        return None

    nadi = re.match(r"Nadi\s+(Overthinking|Stress)\s+([0-9.]+)%\s+\(([^)]+)\)\s+--\s+(.+)", text)
    if nadi:
        param = nadi.group(1)
        value = float(nadi.group(2))
        level = nadi.group(3).strip().title()
        note = nadi.group(4).rstrip(".").strip()
    else:
        legacy_nadi = re.match(r"Nadi\s+(Overthinking|Stress)\s+\(([^)]+)\)\s+--\s+(.+)", text)
        if legacy_nadi:
            param = legacy_nadi.group(1)
            level = legacy_nadi.group(2).strip().title()
            note = legacy_nadi.group(3).rstrip(".").strip()
            value = {"High": 85.0, "Medium": 60.0, "Low": 25.0}.get(level, 50.0)
        else:
            biowell = re.match(
                r"BioWell\s+Psychological(?:\s+balance\s+between\s+sympathetic/parasympathetic\s+nervous\s+system)?\s+([0-9.]+)x10\^-2\s+Joules\s+--\s+([^:]+):\s+(.+)",
                text,
            )
            if not biowell:
                return None
            value = float(biowell.group(1))
            level = biowell.group(2).strip().title()
            note = biowell.group(3).rstrip(".").strip()
            css = "good" if level.lower() == "optimal" else "critical" if level.lower() == "high" else "attention"
            return {
                "label": "Sympathetic / parasympathetic balance",
                "value": f"{value:g}x10^-2 J",
                "status": level,
                "class": css,
                "marker": max(0, min(100, value / 3 * 100)),
                "note": note,
            }

    css = "good" if level.lower() == "low" else "critical" if level.lower() == "high" else "attention"
    return {
        "label": f"{param} level",
        "value": f"{value:g}%",
        "status": level,
        "class": css,
        "marker": max(0, min(100, value)),
        "note": note,
    }


def _emotional_summary_signal(point: str) -> dict | None:
    """Parse emotional summary points into Page 1 signal rows."""
    text = str(point or "").strip()
    if not text:
        return None

    nadi = re.match(r"Nadi\s+Emotional\s+stress\s+([0-9.]+)%\s+\(([^)]+)\)\s+--\s+(.+)", text)
    if not nadi:
        nadi = re.match(r"Nadi\s+Stress\s+\(([^)]+)\)\s+--\s+(.+)", text)
        if nadi:
            level = nadi.group(1).strip().title()
            note = nadi.group(2).rstrip(".").strip()
            value = {"High": 85.0, "Medium": 60.0, "Low": 25.0}.get(level, 50.0)
        else:
            level = note = None
            value = None
    else:
        value = float(nadi.group(1))
        level = nadi.group(2).strip().title()
        note = nadi.group(3).rstrip(".").strip()

    if level and note is not None and value is not None:
        css = "good" if level.lower() == "low" else "critical" if level.lower() == "high" else "attention"
        return {
            "label": "Nadi emotional stress",
            "value": f"{value:g}%",
            "status": level,
            "class": css,
            "marker": max(0, min(100, value)),
            "note": note,
        }

    biowell = re.match(r"BioWell\s+Stress\s+level\s+([0-9.]+)x10\^-2\s+Joules\s+--\s+([^:]+):\s+(.+)", text)
    if biowell:
        value = float(biowell.group(1))
        level = biowell.group(2).strip().title()
        note = biowell.group(3).rstrip(".").strip()
        css = "good" if level.lower() == "optimal" else "critical" if level.lower() == "high" else "attention"
        return {
            "label": "BioWell stress level",
            "value": f"{value:g}x10^-2 J",
            "status": level,
            "class": css,
            "marker": max(0, min(100, value / 3 * 100)),
            "note": note,
        }

    biowell_pct = re.match(r"BioWell\s+Stress\s+level\s+([0-9.]+)%\s+\(([^)]+)\)\s+--\s+(.+)", text)
    if biowell_pct:
        value = float(biowell_pct.group(1))
        level = biowell_pct.group(2).strip().title()
        note = biowell_pct.group(3).rstrip(".").strip()
        css = "good" if level.lower() == "low" else "critical" if level.lower() == "high" else "attention"
        return {
            "label": "BioWell stress level",
            "value": f"{value:g}%",
            "status": level,
            "class": css,
            "marker": max(0, min(100, value)),
            "note": note,
        }

    biowell_level = re.match(r"BioWell\s+Stress\s+level\s+--\s+(.+)", text)
    if biowell_level:
        note = biowell_level.group(1).rstrip(".").strip()
        return {
            "label": "BioWell stress level",
            "value": "--",
            "status": "Observed",
            "class": "attention",
            "marker": 50,
            "note": note,
        }

    emotional = re.match(r"BioWell\s+Emotional\s+level\s+--\s+(.+)", text)
    if emotional:
        note = emotional.group(1).rstrip(".").strip()
        return {
            "label": "BioWell emotional level",
            "value": "--",
            "status": "Observed",
            "class": "attention",
            "marker": 50,
            "note": note,
        }

    chakra = _chakra_summary_signal(text)
    if chakra:
        return chakra

    return None


def _missing_emotional_signal(source: str) -> dict:
    """Return a visible placeholder for unavailable emotional indicators."""
    label = "BioWell stress level" if source.lower() == "biowell" else "Nadi emotional stress"
    return {
        "label": label,
        "value": "--",
        "status": "Not available",
        "class": "attention",
        "marker": 0,
        "note": "Not found in parsed report data",
    }


def _emotional_biowell_stress_alias(signal: dict) -> dict:
    """Mirror the parsed stress row under the BioWell stress label."""
    alias = dict(signal or {})
    alias["label"] = "BioWell stress level"
    return alias


def _chakra_summary_signal(point: str) -> dict | None:
    """Parse chakra summary lines used by emotional/spiritual quadrants."""
    text = str(point or "").strip()
    if not text:
        return None

    chakra = re.match(
        r"(?P<name>[A-Za-z]+)\s+-\s+(?P<color>[A-Za-z ]+)\s+"
        r"(?P<value>[0-9.]+)%\s+\((?P<status>[^)]+)\)\s+--\s+(?P<note>.+)",
        text,
    )
    if not chakra:
        return None

    status = chakra.group("status").strip()
    status_lower = status.lower()
    if status_lower == "normal":
        css = "good"
    elif status_lower == "mild deviation":
        css = "attention"
    else:
        css = "critical"

    color_name = chakra.group("color").strip().title()
    color_key = color_name.lower()
    accent = {
        "red": "#cf3c34",
        "orange": "#f18a1b",
        "yellow": "#d6a400",
        "green": "#239b56",
        "azure": "#2d9cdb",
        "blue": "#266dd3",
        "violet": "#8e44ad",
        "magenta": "#c4459a",
        "light blue": "#2d9cdb",
    }.get(color_key, "#1b5381")

    value = float(chakra.group("value"))
    return {
        "label": f"{chakra.group('name').strip()} - {color_name}",
        "value": f"{value:g}%",
        "status": status,
        "class": css,
        "marker": max(0, min(100, value)),
        "note": chakra.group("note").rstrip(".").strip(),
        "accent": accent,
    }


def _spiritual_summary_signal(point: str) -> dict | None:
    """Parse spiritual chakra lines into compact signal rows."""
    return _chakra_summary_signal(point)


def render_html(report_data: dict) -> str:
    """Render the report data into a complete HTML string.

    Args:
        report_data: Full report dict (patient, metrics, systems, wellness, dimensions).

    Returns:
        Rendered HTML string.
    """
    env = _build_jinja_env()
    template = env.get_template(_TEMPLATE_NAME)

    # Provide default empty dicts so Jinja2 doesn't fail on missing keys
    ctx = {
        "patient":    report_data.get("patient", {}),
        "metrics":    report_data.get("metrics", {}),
        "systems":    report_data.get("systems", {}),
        "wellness":   report_data.get("wellness", {}),
        "dimensions": report_data.get("dimensions", {
            "physical":      {"score": 0, "description": ""},
            "psychological": {"score": 0, "description": ""},
            "emotional":     {"score": 0, "description": ""},
            "spiritual":     {"score": 0, "description": ""},
        }),
        "interpretations": report_data.get("interpretations", {}),
        "dmit":       report_data.get("dmit", {}),
        "biorhythm":  report_data.get("biorhythm", {}),
        "system_summaries": report_data.get("system_summaries", {}),
        "swot":       report_data.get("swot", {}),
    }
    ctx["wellness_view"] = _wellness_view(
        ctx["wellness"],
        report_data.get("food_recommendations", {}),
    )

    # Convert biorhythm image file to base64 data URI for inline embedding
    bio = ctx["biorhythm"]
    if bio.get("calendar"):
        from app.engine.biorhythm_calculator import normalize_biorhythm_calendar

        bio["calendar"] = normalize_biorhythm_calendar(bio["calendar"])

    if bio.get("image_path"):
        img_path = Path(bio["image_path"])
        if img_path.exists():
            import base64
            img_bytes = img_path.read_bytes()
            b64 = base64.b64encode(img_bytes).decode("ascii")
            bio["image_data_uri"] = f"data:image/png;base64,{b64}"
            log.info(f"Biorhythm image encoded as base64 ({len(img_bytes)} bytes)")
        else:
            log.warning(f"Biorhythm image not found: {img_path}")

    return template.render(**ctx)


async def _render_pdf_async(html: str, output_path: str) -> str:
    """Use Playwright to convert HTML to an A4 PDF."""
    # pyrefly: ignore [missing-import]
    from playwright.async_api import async_playwright

    # Write HTML to a temp file in the template dir so file:/// image
    # paths resolve correctly (same-origin as the SVG/PNG assets).
    tmp_html = _TEMPLATE_DIR / "_render_tmp.html"
    tmp_html.write_text(html, encoding="utf-8")

    try:
        async with async_playwright() as p:
            chrome_path = (
                os.getenv("CHROME_PATH")
                or shutil.which("google-chrome")
                or shutil.which("google-chrome-stable")
                or shutil.which("chromium")
                or shutil.which("chromium-browser")
            )
            launch_options = {"headless": True}
            if chrome_path:
                launch_options["executable_path"] = chrome_path
            browser = await p.chromium.launch(**launch_options)
            # Viewport = 210mm at 96 DPI ≈ 794px
            page = await browser.new_page(viewport={"width": 794, "height": 1123})

            # Emulate print media so @media print rules activate
            await page.emulate_media(media="print")

            # Navigate to the file — this allows file:/// image paths to load
            file_url = tmp_html.resolve().as_uri()
            await page.goto(file_url, wait_until="networkidle")

            # Give fonts + SVGs a moment to fully render
            await page.wait_for_timeout(800)

            # Generate PDF — let CSS @page control the size
            await page.pdf(
                path=output_path,
                prefer_css_page_size=True,
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )

            await browser.close()
    finally:
        # Clean up temp file
        if tmp_html.exists():
            tmp_html.unlink()

    log.info(f"PDF rendered: {output_path}")
    return output_path


def render_pdf(report_data: dict, output_path: str) -> str:
    """Synchronous wrapper: render report data to PDF.

    Args:
        report_data: Full report dict.
        output_path: Where to write the PDF.

    Returns:
        The output path.
    """
    html = render_html(report_data)
    return asyncio.run(_render_pdf_async(html, output_path))


async def render_pdf_async(report_data: dict, output_path: str) -> str:
    """Async wrapper: render report data to PDF from an existing event loop."""
    html = render_html(report_data)
    return await _render_pdf_async(html, output_path)


def render_pdf_from_json(json_path: str, output_path: str) -> str:
    """Convenience: load a report.json and render PDF.

    Args:
        json_path:   Path to report.json.
        output_path: Where to write the PDF.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return render_pdf(data, output_path)


# ── CLI entrypoint for testing ───────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m app.output.html_renderer <report.json> [output.pdf]")
        sys.exit(1)

    json_file = sys.argv[1]
    pdf_file = sys.argv[2] if len(sys.argv) > 2 else "test_output.pdf"

    print(f"Rendering {json_file} -> {pdf_file} ...")
    render_pdf_from_json(json_file, pdf_file)
    print(f"Done! PDF saved to {pdf_file}")
