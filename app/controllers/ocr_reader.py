"""Shared EasyOCR reader initialization.

EasyOCR downloads model files on first use. The extraction pipeline can run
PDF and image OCR concurrently, so guard initialization to avoid competing
downloads corrupting the shared ~/.EasyOCR cache.
"""
import logging
from functools import lru_cache
from threading import Lock

log = logging.getLogger(__name__)

_reader_lock = Lock()


@lru_cache(maxsize=1)
def _build_reader():
    import easyocr
    import torch

    use_gpu = torch.cuda.is_available()
    log.info(f"EasyOCR: GPU={'yes' if use_gpu else 'no (CPU)'}")
    return easyocr.Reader(["en"], gpu=use_gpu)


def get_easyocr_reader():
    with _reader_lock:
        return _build_reader()
