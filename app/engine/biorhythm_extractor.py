"""Extract the biorhythm graph image from a BioWell PDF using PyMuPDF.

Scans pages for the BioWell biorhythm section, then extracts the embedded
chart image and saves it as PNG.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pymupdf as fitz

log = logging.getLogger(__name__)

_MIN_CHART_AREA = 250_000
_CHART_RATIO_MIN = 1.15
_CHART_RATIO_MAX = 2.05


def _biorhythm_image_score(img_info: tuple) -> tuple[int, int]:
    """Score PDF images, preferring large wide chart-like images."""
    width = int(img_info[2] or 0)
    height = int(img_info[3] or 0)
    if width <= 0 or height <= 0:
        return (0, 0)

    area = width * height
    ratio = width / height
    looks_like_chart = (
        area >= _MIN_CHART_AREA
        and _CHART_RATIO_MIN <= ratio <= _CHART_RATIO_MAX
    )
    return (1 if looks_like_chart else 0, area)


def extract_biorhythm_image(
    pdf_path: str,
    output_path: str | None = None,
) -> str | None:
    """Extract the biorhythm chart image from a BioWell PDF.

    Args:
        pdf_path:    Path to the BioWell PDF file.
        output_path: Where to save the PNG.  Defaults to
                     ``<pdf_dir>/biorhythm_graph.png``.

    Returns:
        The output path on success, or ``None`` if the biorhythm page
        was not found or had no extractable images.
    """
    if output_path is None:
        output_path = str(Path(pdf_path).parent / "biorhythm_graph.png")

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        log.warning(f"Could not open BioWell PDF for biorhythm extraction: {e}")
        return None

    try:
        # ── 1. Find the biorhythm page ───────────────────────────────
        biorhythm_page = None
        for page in doc:
            text = page.get_text("text", clip=None)[:1000].lower()
            if "biorhythm" in text:
                biorhythm_page = page
                break

        if biorhythm_page is None:
            log.info("No biorhythm page found in BioWell PDF")
            return None

        page_num = biorhythm_page.number + 1
        log.info(f"Biorhythm page found: page {page_num}")

        # ── 2. Extract the chart image on that page ──────────────────
        images = biorhythm_page.get_images(full=True)
        if not images:
            log.info(f"Page {page_num} has no embedded images")
            return None

        best_img = None
        best_score = (0, 0)
        best_dimensions = (0, 0)
        for img_info in images:
            xref = img_info[0]
            width = int(img_info[2] or 0)
            height = int(img_info[3] or 0)
            score = _biorhythm_image_score(img_info)
            if score > best_score:
                best_score = score
                best_img = xref
                best_dimensions = (width, height)

        if best_img is None:
            log.info("Could not identify biorhythm chart image")
            return None

        # ── 3. Extract raw image bytes and save ──────────────────────
        base_image = doc.extract_image(best_img)
        if not base_image:
            log.warning("Failed to extract image bytes from PDF")
            return None

        img_bytes = base_image["image"]
        ext = base_image.get("ext", "png")

        # Always save as PNG for consistency
        if ext != "png":
            from PIL import Image
            import io
            pil_img = Image.open(io.BytesIO(img_bytes))
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            img_bytes = buf.getvalue()

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(img_bytes)
        log.info(
            f"Biorhythm graph extracted: {best_dimensions[0] * best_dimensions[1]} px "
            f"({base_image.get('width', '?')}x{base_image.get('height', '?')}) "
            f"→ {output_path}"
        )
        return output_path

    finally:
        doc.close()
