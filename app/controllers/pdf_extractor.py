"""PDF -> plain-text extractor with OCR fallback for scanned PDFs.

OCR fallback strategy:
  1. Try pdfplumber text extraction first
  2. If < MIN_CHARS_PER_PAGE, render page to image and OCR
  3. Images are downscaled to MAX_OCR_IMAGE_WIDTH to prevent memory crashes
  4. OCR failures are logged and skipped (graceful degradation)
"""
import io
import logging
import asyncio

import pdfplumber
from PIL import Image, ImageEnhance
import numpy as np

from app.controllers.base import BaseExtractor, ExtractionResult
from app.controllers.ocr_reader import get_easyocr_reader

log = logging.getLogger(__name__)

# Minimum chars per page to consider text extraction successful.
# Below this, we fall back to OCR.
MIN_CHARS_PER_PAGE = 50

# Max image width for OCR — prevents memory crashes on large pages
MAX_OCR_IMAGE_WIDTH = 1200

# Max pages to OCR per document — prevents excessive processing time
MAX_OCR_PAGES = 15

# Render resolution for OCR (lower = faster, less accurate)
OCR_RENDER_DPI = 150


class PDFExtractor(BaseExtractor):
    """Extracts text from PDF reports.

    Uses pdfplumber for text-based PDFs. Falls back to OCR
    (page -> image -> easyocr) when text extraction yields too little.
    """

    async def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        device = filename
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._extract_sync, file_bytes, filename
            )
            return result
        except Exception as e:
            return ExtractionResult(
                device=device, raw_text="", error=f"PDF extraction failed: {e}"
            )

    @staticmethod
    def _extract_sync(file_bytes: bytes, filename: str) -> ExtractionResult:
        """Synchronous extraction: text first, OCR fallback per page."""
        text_parts: list[str] = []
        ocr_pages = 0
        ocr_failures = 0
        page_count = 0

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page_count = len(pdf.pages)

            for i, page in enumerate(pdf.pages):
                # ── Try text extraction first ────────────────────────
                page_text = page.extract_text() or ""

                # Also grab tables
                tables = page.extract_tables() or []
                table_text_parts = []
                for table in tables:
                    for row in table:
                        cleaned = [str(cell).strip() if cell else "" for cell in row]
                        table_text_parts.append(" | ".join(cleaned))

                combined = page_text
                if table_text_parts:
                    combined += "\n[TABLE]\n" + "\n".join(table_text_parts)

                # ── Check if we got enough text ──────────────────────
                if len(combined.strip()) >= MIN_CHARS_PER_PAGE:
                    text_parts.append(combined.strip())
                    continue

                # ── OCR fallback: render page to image ───────────────
                # Skip if we've already OCR'd too many pages
                if ocr_pages >= MAX_OCR_PAGES:
                    log.info(
                        f"Page {i+1}/{page_count}: Skipping OCR "
                        f"(max {MAX_OCR_PAGES} pages reached)"
                    )
                    if combined.strip():
                        text_parts.append(combined.strip())
                    continue

                log.info(
                    f"Page {i+1}/{page_count}: only {len(combined.strip())} chars "
                    f"— falling back to OCR"
                )
                try:
                    ocr_text = PDFExtractor._ocr_page(page)
                    if ocr_text.strip():
                        text_parts.append(f"[OCR Page {i+1}]\n{ocr_text.strip()}")
                        ocr_pages += 1
                    elif combined.strip():
                        text_parts.append(combined.strip())
                except Exception as e:
                    ocr_failures += 1
                    log.warning(f"OCR failed on page {i+1}: {e}")
                    if combined.strip():
                        text_parts.append(combined.strip())

        raw_text = "\n\n--- PAGE BREAK ---\n\n".join(text_parts)

        if not raw_text.strip():
            return ExtractionResult(
                device=filename,
                raw_text="",
                page_count=page_count,
                error="PDF contained no extractable text (text + OCR both failed).",
            )

        log.info(
            f"{filename}: {len(raw_text)} chars from {page_count} pages "
            f"(OCR: {ocr_pages} pages, {ocr_failures} failures)"
        )

        return ExtractionResult(
            device=filename,
            raw_text=raw_text.strip(),
            page_count=page_count,
            metadata={
                "source": filename,
                "ocr_pages": ocr_pages,
                "ocr_failures": ocr_failures,
                "total_pages": page_count,
            },
        )

    @staticmethod
    def _ocr_page(page) -> str:
        """Convert a pdfplumber page to image and run OCR.

        Images are downscaled to MAX_OCR_IMAGE_WIDTH to prevent
        memory crashes (WinError 0xc000001d) on large pages.
        """
        # Render page to PIL Image
        pil_img = page.to_image(resolution=OCR_RENDER_DPI).original
        pil_img = pil_img.convert("RGB")

        # ── Downscale if too large ───────────────────────────────
        w, h = pil_img.size
        if w > MAX_OCR_IMAGE_WIDTH:
            ratio = MAX_OCR_IMAGE_WIDTH / w
            new_size = (MAX_OCR_IMAGE_WIDTH, int(h * ratio))
            pil_img = pil_img.resize(new_size, Image.LANCZOS)
            log.info(f"  Downscaled {w}x{h} -> {new_size[0]}x{new_size[1]}")

        # Enhance for better OCR
        pil_img = ImageEnhance.Contrast(pil_img).enhance(1.5)
        pil_img = ImageEnhance.Sharpness(pil_img).enhance(1.5)

        img_array = np.array(pil_img)

        reader = get_easyocr_reader()
        results = reader.readtext(img_array, detail=1)

        # Sort top-to-bottom, left-to-right
        results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))

        # Group into lines by Y proximity
        lines: list[list[str]] = []
        current_line: list[str] = []
        last_y = -999

        for bbox, text, conf in results:
            if conf < 0.15:
                continue
            top_y = bbox[0][1]
            if abs(top_y - last_y) > 15:
                if current_line:
                    lines.append(current_line)
                current_line = [text]
            else:
                current_line.append(text)
            last_y = top_y

        if current_line:
            lines.append(current_line)

        return "\n".join(" ".join(line) for line in lines)
