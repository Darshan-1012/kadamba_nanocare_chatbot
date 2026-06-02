"""Image → text extractor using EasyOCR (for InBody report)."""
import io
import asyncio

from PIL import Image, ImageEnhance
import numpy as np

from app.controllers.base import BaseExtractor, ExtractionResult
from app.controllers.ocr_reader import get_easyocr_reader


class ImageExtractor(BaseExtractor):
    """OCR extraction for image-based reports (InBody)."""

    async def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        device = "inbody"
        try:
            # Run OCR in a thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._ocr_sync, file_bytes)
            return ExtractionResult(
                device=device,
                raw_text=result,
                page_count=1,
                metadata={"source": filename, "method": "easyocr"},
            )
        except Exception as e:
            return ExtractionResult(
                device=device,
                raw_text="",
                error=f"Image OCR failed: {str(e)}",
            )

    @staticmethod
    def _ocr_sync(file_bytes: bytes) -> str:
        """Synchronous OCR pipeline: pre-process → EasyOCR → text."""
        # 1. Load and pre-process
        img = Image.open(io.BytesIO(file_bytes))

        # Convert to RGB if needed
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Enhance contrast and sharpness for better OCR
        img = ImageEnhance.Contrast(img).enhance(1.5)
        img = ImageEnhance.Sharpness(img).enhance(2.0)

        # Convert to numpy array for EasyOCR
        img_array = np.array(img)

        # 2. Run OCR
        reader = get_easyocr_reader()
        results = reader.readtext(img_array, detail=1)

        # 3. Sort by vertical position (top→bottom), then horizontal (left→right)
        results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))

        # 4. Group into lines by Y proximity
        lines: list[list[str]] = []
        current_line: list[str] = []
        last_y = -999

        for bbox, text, conf in results:
            if conf < 0.2:  # skip very low confidence
                continue
            top_y = bbox[0][1]
            if abs(top_y - last_y) > 15:  # new line threshold
                if current_line:
                    lines.append(current_line)
                current_line = [text]
            else:
                current_line.append(text)
            last_y = top_y

        if current_line:
            lines.append(current_line)

        return "\n".join(" ".join(line) for line in lines)
