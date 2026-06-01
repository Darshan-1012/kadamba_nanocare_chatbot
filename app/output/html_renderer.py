"""Render Jinja2 template → HTML → PDF via Playwright (headless Chromium).

Usage:
    from app.output.html_renderer import render_pdf
    render_pdf(report_data, output_path="report.pdf")
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

# pyrefly: ignore [missing-import]
from jinja2 import Environment, FileSystemLoader

log = logging.getLogger(__name__)

# Paths
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "frontend" / "template"
_TEMPLATE_NAME = "report_template.html"


def _build_jinja_env() -> Environment:
    """Create a Jinja2 environment with the template directory."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,  # HTML is pre-authored; no double-escaping
    )


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
    return template.render(**ctx)


async def _render_pdf_async(html: str, output_path: str) -> str:
    """Use Playwright to convert HTML to an A4 PDF."""
    # pyrefly: ignore [missing-import]
    from playwright.async_api import async_playwright
    import tempfile, os

    # Write HTML to a temp file in the template dir so file:/// image
    # paths resolve correctly (same-origin as the SVG/PNG assets).
    tmp_html = _TEMPLATE_DIR / "_render_tmp.html"
    tmp_html.write_text(html, encoding="utf-8")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
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
