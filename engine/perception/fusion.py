# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Fusion layer — merges UIA, Vision, and OCR element lists into one
deduplicated, confidence-ranked list.

Strategy
--------
1. Start with all UIA (Tier 1) elements — these have exact bounding boxes
   and full action metadata, so they are the ground truth.
2. Add Vision (Tier 3) elements that do not overlap any existing element by
   ≥ IOU_THRESHOLD.  Vision elements get capped confidence.
3. Add OCR (Tier 4) elements that do not overlap any existing element by
   ≥ IOU_THRESHOLD.  OCR elements have the lowest confidence cap.
4. Sort the merged list descending by confidence.

Tier priority when two elements overlap beyond the threshold:
    ACCESSIBILITY > VISION > OCR
So a UIA element always wins over a Vision or OCR duplicate.

Usage
-----
    from engine.perception.fusion import fuse_elements

    merged = fuse_elements(uia_elements, vision_elements, ocr_elements)
"""

from __future__ import annotations

from typing import Sequence

from engine.types import BoundingBox, Element, PerceptionTier

# IoU threshold above which two elements are considered duplicates.
IOU_THRESHOLD = 0.7

# Confidence caps for non-UIA tiers (prevent them from outranking UIA hits
# that sit near the confidence boundary).
_VISION_CONF_CAP = 0.95
_OCR_CONF_CAP    = 0.85


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fuse_elements(
    uia: Sequence[Element],
    vision: Sequence[Element] | None = None,
    ocr: Sequence[Element] | None = None,
    iou_threshold: float = IOU_THRESHOLD,
) -> list[Element]:
    """
    Merge UIA, Vision, and OCR element lists into one deduplicated list.

    Parameters
    ----------
    uia : sequence of Element
        Elements from the accessibility (UIA) tier.  These always win.
    vision : sequence of Element, optional
        Elements from the YOLO vision tier.
    ocr : sequence of Element, optional
        Elements from the Tesseract OCR tier.
    iou_threshold : float
        Intersection-over-union threshold above which two elements are
        considered duplicates (default 0.7).

    Returns
    -------
    list[Element]
        Merged, deduplicated list sorted by confidence descending.
        UIA elements always appear; lower-tier elements only appear when
        they do not substantially overlap any already-accepted element.
    """
    merged: list[Element] = list(uia)

    for el in (vision or []):
        capped = _cap_confidence(el, _VISION_CONF_CAP)
        if not _overlaps_any(capped, merged, iou_threshold):
            merged.append(capped)

    for el in (ocr or []):
        capped = _cap_confidence(el, _OCR_CONF_CAP)
        if not _overlaps_any(capped, merged, iou_threshold):
            merged.append(capped)

    merged.sort(key=lambda e: e.confidence, reverse=True)
    return merged


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _iou(a: BoundingBox, b: BoundingBox) -> float:
    """Intersection-over-Union of two bounding boxes."""
    ix1 = max(a.x, b.x)
    iy1 = max(a.y, b.y)
    ix2 = min(a.x + a.width,  b.x + b.width)
    iy2 = min(a.y + a.height, b.y + b.height)

    inter_w = max(0, ix2 - ix1)
    inter_h = max(0, iy2 - iy1)
    inter   = inter_w * inter_h

    if inter == 0:
        return 0.0

    area_a = a.width  * a.height
    area_b = b.width  * b.height
    union  = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _overlaps_any(
    el: Element,
    existing: list[Element],
    threshold: float,
) -> bool:
    """Return True if *el* overlaps any element in *existing* by ≥ threshold."""
    for other in existing:
        if _iou(el.bbox, other.bbox) >= threshold:
            return True
    return False


def _cap_confidence(el: Element, cap: float) -> Element:
    """Return a copy of *el* with confidence clamped to *cap*."""
    if el.confidence <= cap:
        return el
    # Shallow copy via dataclass replace pattern
    from dataclasses import replace
    return replace(el, confidence=cap)


__all__ = ["fuse_elements", "IOU_THRESHOLD"]
