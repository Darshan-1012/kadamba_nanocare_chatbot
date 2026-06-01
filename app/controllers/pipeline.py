"""Extraction pipeline — orchestrates all 5 device file extractions."""
import asyncio
from typing import Dict

from app.config import PDF_DEVICES, IMAGE_DEVICES
from app.controllers.base import ExtractionResult
from app.controllers.pdf_extractor import PDFExtractor
from app.controllers.image_extractor import ImageExtractor


# Singleton extractors
_pdf_extractor = PDFExtractor()
_img_extractor = ImageExtractor()


async def extract_all(
    files: Dict[str, tuple[bytes, str]],
) -> Dict[str, ExtractionResult]:
    """Extract text from all uploaded device files in parallel.

    Args:
        files: Mapping of device_key → (file_bytes, original_filename).
               Expected keys: ecg, nadi, biowell, biores, inbody.

    Returns:
        Mapping of device_key → ExtractionResult.
    """
    tasks = {}

    for device_key, (file_bytes, filename) in files.items():
        if device_key in PDF_DEVICES:
            tasks[device_key] = _extract_pdf(device_key, file_bytes, filename)
        elif device_key in IMAGE_DEVICES:
            tasks[device_key] = _extract_image(device_key, file_bytes, filename)
        else:
            # Unknown device — skip
            continue

    # Run all extractions in parallel (CPU-bound, no GPU needed)
    keys = list(tasks.keys())
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    output: Dict[str, ExtractionResult] = {}
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            output[key] = ExtractionResult(
                device=key, raw_text="", error=str(result)
            )
        else:
            result.device = key  # ensure correct device label
            output[key] = result

    return output


async def _extract_pdf(
    device_key: str, file_bytes: bytes, filename: str
) -> ExtractionResult:
    """Extract text from a PDF file."""
    result = await _pdf_extractor.extract(file_bytes, filename)
    result.device = device_key
    return result


async def _extract_image(
    device_key: str, file_bytes: bytes, filename: str
) -> ExtractionResult:
    """Extract text from an image file via OCR."""
    result = await _img_extractor.extract(file_bytes, filename)
    result.device = device_key
    return result
