"""Abstract base for all device-report extractors."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ExtractionResult:
    """Standardised output from every extractor."""
    device: str                     # e.g. "ecg", "nadi", "inbody"
    raw_text: str                   # full extracted text
    page_count: int = 1             # number of pages / frames processed
    metadata: dict = field(default_factory=dict)   # device-specific extras
    error: Optional[str] = None     # non-None when extraction failed


class BaseExtractor(ABC):
    """Every device extractor must implement `extract`."""

    @abstractmethod
    async def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        """Read raw bytes and return structured text.

        Args:
            file_bytes: Raw uploaded file content.
            filename:   Original filename (for extension checks).

        Returns:
            ExtractionResult with the extracted text or an error.
        """
        ...
