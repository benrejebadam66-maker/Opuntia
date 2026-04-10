# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
OCR fallback perception — Tier 4.

Uses pytesseract (Tesseract 5) to extract text blocks and their bounding
boxes from a screenshot or image crop.  Converts each text block into an
Element so the fusion layer can merge it with UIA / vision results.

When Tesseract / pytesseract is not installed the function returns an empty
list and logs a one-time warning.

Usage
-----
    from engine.perception.ocr import extract_text_elements

    elements = extract_text_elements(frame)   # frame: np.ndarray H×W×3
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)
_TESSERACT_WARNING_ISSUED = False

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]
    _NUMPY_AVAILABLE = False

try:
    import pytesseract
    _TESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore[assignment]
    _TESSERACT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_text_elements(
    frame: object,
    lang: str = "eng",
    min_confidence: float = 60.0,
    min_text_len: int = 2,
) -> list:
    """
    Extract text blocks from a screenshot via Tesseract OCR.

    Parameters
    ----------
    frame : numpy.ndarray (H × W × 3, uint8) or PIL.Image or None
        Image to analyse.
    lang : str
        Tesseract language code (default ``"eng"``).
    min_confidence : float
        Minimum Tesseract word-level confidence (0–100) to include.
    min_text_len : int
        Minimum non-whitespace character count to include a block.

    Returns
    -------
    list[Element]
        Detected text elements with ``source_tier=OCR``.
    """
    global _TESSERACT_WARNING_ISSUED

    if frame is None:
        return []

    if not _TESSERACT_AVAILABLE:
        if not _TESSERACT_WARNING_ISSUED:
            logger.warning(
                "pytesseract not installed — OCR fallback (Tier 4) disabled. "
                "Install with: pip install pytesseract"
            )
            _TESSERACT_WARNING_ISSUED = True
        return []

    if not _NUMPY_AVAILABLE:
        logger.warning("numpy not available — OCR perception skipped")
        return []

    try:
        img = _to_pil(frame)
        if img is None:
            return []
        return _run_ocr(img, lang, min_confidence, min_text_len)
    except Exception as exc:
        logger.error("OCR extraction failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _to_pil(frame: object):
    """Convert frame to PIL.Image.  Returns None on failure."""
    try:
        from PIL import Image as _PILImage
        if isinstance(frame, _PILImage.Image):
            return frame.convert("RGB")
        if _NUMPY_AVAILABLE and isinstance(frame, np.ndarray):
            arr = frame[..., :3] if frame.ndim == 3 else frame
            return _PILImage.fromarray(arr.astype("uint8"))
        return None
    except Exception as exc:
        logger.debug("_to_pil error: %s", exc)
        return None


def _run_ocr(img, lang: str, min_conf: float, min_len: int) -> list:
    """Run pytesseract data extraction and convert to Element list."""
    from engine.types import BoundingBox, Element, ElementState, PerceptionTier

    try:
        data = pytesseract.image_to_data(
            img,
            lang=lang,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as exc:
        logger.error("pytesseract.image_to_data failed: %s", exc)
        return []

    elements: list = []
    n = len(data.get("text", []))
    id_counter = 0

    for i in range(n):
        text = (data["text"][i] or "").strip()
        if len(text) < min_len:
            continue
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = 0.0
        if conf < min_conf:
            continue

        x = int(data["left"][i])
        y = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])
        if w <= 0 or h <= 0:
            continue

        bbox = BoundingBox(x=x, y=y, width=w, height=h)
        el_id = f"ocr_{id_counter:03d}"
        id_counter += 1

        elements.append(Element(
            id=el_id,
            label=text,
            control_type="Text",
            bbox=bbox,
            actions=["read"],
            state=ElementState(),
            confidence=conf / 100.0,
            source_tier=PerceptionTier.OCR,
        ))

    return elements


__all__ = ["extract_text_elements"]
