# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Perception pipeline — Phase 2: tiered UIA + Vision + OCR pipeline.

Tier order
----------
1. ACCESSIBILITY  — Windows UI Automation (always runs)
2. VISION         — YOLOv8-nano ONNX (runs when model present & frame changed)
3. OCR            — Tesseract (runs when pytesseract installed & frame changed)

Visual diffing gates Tiers 2-3: if the screen has not changed since the last
call (Hamming ratio < 5 %), the cached result is returned immediately and the
expensive YOLO/Tesseract passes are skipped.

Usage
-----
    from engine.perception import perceive

    # Accessibility only (fast, no frame needed):
    elements = await perceive()

    # Full pipeline with a captured frame:
    import numpy as np
    frame = ...  # np.ndarray H×W×3 uint8
    elements = await perceive(frame=frame)

    # Opt-in tiers:
    elements = await perceive(frame=frame, tier="vision")   # UIA + vision
    elements = await perceive(frame=frame, tier="ocr")      # UIA + vision + OCR
    elements = await perceive(frame=frame, tier="all")      # same as "ocr"
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from engine.types import ElementMap
from engine.perception.accessibility import perceive_accessibility
from engine.perception.diffing import compute_frame_hash, is_frame_unchanged
from engine.perception.fusion import fuse_elements

logger = logging.getLogger(__name__)

# Module-level cache for visual diffing
_prev_hash: Optional[str] = None
_cached_map: Optional[ElementMap] = None


async def perceive(
    app_name: Optional[str] = None,
    hwnd: Optional[int] = None,
    frame: object = None,
    tier: str = "accessibility",
    diff_threshold: float = 0.05,
) -> ElementMap:
    """
    Main perception entry point — tiered UIA + Vision + OCR pipeline.

    Parameters
    ----------
    app_name : str, optional
        Window title substring — scans only that window if given.
    hwnd : int, optional
        Specific window handle to scan.
    frame : numpy.ndarray (H×W×3, uint8) or PIL.Image, optional
        Current screenshot.  Required for vision and OCR tiers.
        When None, only the accessibility tier runs.
    tier : str
        Which tiers to activate:
        - ``"accessibility"``  — UIA only (default, fast)
        - ``"vision"``         — UIA + YOLO vision
        - ``"ocr"`` / ``"all"``— UIA + YOLO + Tesseract OCR
    diff_threshold : float
        Hamming ratio below which the frame is considered unchanged and
        vision/OCR passes are skipped (default 0.05 = 5 %).

    Returns
    -------
    ElementMap
        Merged, deduplicated snapshot of all discovered elements.
    """
    global _prev_hash, _cached_map

    # --- Tier 1: Accessibility (always) ---
    uia_elements = await perceive_accessibility(app_name=app_name, hwnd=hwnd)

    # If no frame or only accessibility requested, return UIA result directly.
    tier_lower = tier.lower()
    if frame is None or tier_lower == "accessibility":
        return ElementMap(
            elements=uia_elements,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # --- Visual diffing gate for Tiers 2-3 ---
    curr_hash = compute_frame_hash(frame)
    unchanged, diff_ratio = is_frame_unchanged(frame, _prev_hash, diff_threshold)

    if unchanged and _cached_map is not None:
        logger.debug(
            "Screen unchanged (diff=%.3f) — reusing cached vision/OCR result", diff_ratio
        )
        # Still merge with fresh UIA scan (accessibility is cheap)
        fused = fuse_elements(
            uia_elements,
            [e for e in _cached_map.elements
             if e.source_tier.value != "accessibility"],
        )
        return ElementMap(
            elements=fused,
            timestamp=datetime.now(timezone.utc).isoformat(),
            screen_hash=curr_hash,
            diff_ratio=diff_ratio,
        )

    vision_elements: list = []
    ocr_elements: list    = []

    # --- Tier 2: Vision (YOLO) ---
    if tier_lower in ("vision", "ocr", "all"):
        try:
            from engine.perception.vision import detect_ui_elements
            vision_elements = detect_ui_elements(frame)
        except Exception as exc:
            logger.warning("Vision tier failed: %s", exc)

    # --- Tier 3: OCR (Tesseract) ---
    if tier_lower in ("ocr", "all"):
        try:
            from engine.perception.ocr import extract_text_elements
            ocr_elements = extract_text_elements(frame)
        except Exception as exc:
            logger.warning("OCR tier failed: %s", exc)

    # --- Fusion ---
    fused = fuse_elements(uia_elements, vision_elements, ocr_elements)

    result = ElementMap(
        elements=fused,
        timestamp=datetime.now(timezone.utc).isoformat(),
        screen_hash=curr_hash,
        diff_ratio=diff_ratio,
    )

    # Update cache
    _prev_hash  = curr_hash
    _cached_map = result

    return result


__all__ = ["perceive"]
