# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Unit tests for engine.perception.fusion.
"""

import unittest

from engine.types import BoundingBox, Element, ElementState, PerceptionTier
from engine.perception.fusion import fuse_elements, IOU_THRESHOLD


def _el(
    el_id: str,
    x: int, y: int, w: int, h: int,
    tier: PerceptionTier = PerceptionTier.ACCESSIBILITY,
    confidence: float = 1.0,
    label: str = "Label",
    control_type: str = "Button",
) -> Element:
    return Element(
        id=el_id,
        label=label,
        control_type=control_type,
        bbox=BoundingBox(x=x, y=y, width=w, height=h),
        actions=["click"],
        state=ElementState(),
        confidence=confidence,
        source_tier=tier,
    )


class TestFuseElementsBasic(unittest.TestCase):
    def test_empty_all_returns_empty(self):
        result = fuse_elements([], [], [])
        self.assertEqual(result, [])

    def test_uia_only_passthrough(self):
        uia = [_el("u1", 0, 0, 100, 30), _el("u2", 0, 50, 100, 30)]
        result = fuse_elements(uia)
        self.assertEqual(len(result), 2)

    def test_none_vision_ocr_accepted(self):
        uia = [_el("u1", 0, 0, 100, 30)]
        result = fuse_elements(uia, None, None)
        self.assertEqual(len(result), 1)

    def test_non_overlapping_vision_added(self):
        uia    = [_el("u1", 0, 0, 50, 50, tier=PerceptionTier.ACCESSIBILITY)]
        vision = [_el("v1", 200, 200, 50, 50, tier=PerceptionTier.VISION, confidence=0.8)]
        result = fuse_elements(uia, vision)
        self.assertEqual(len(result), 2)

    def test_non_overlapping_ocr_added(self):
        uia = [_el("u1", 0, 0, 50, 50)]
        ocr = [_el("o1", 300, 300, 60, 20, tier=PerceptionTier.OCR, confidence=0.75)]
        result = fuse_elements(uia, [], ocr)
        self.assertEqual(len(result), 2)


class TestFuseElementsDeduplication(unittest.TestCase):
    def test_fully_overlapping_vision_suppressed(self):
        """Vision element that perfectly overlaps a UIA element should be dropped."""
        uia    = [_el("u1", 10, 10, 80, 30)]
        vision = [_el("v1", 10, 10, 80, 30, tier=PerceptionTier.VISION, confidence=0.9)]
        result = fuse_elements(uia, vision)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "u1")

    def test_fully_overlapping_ocr_suppressed(self):
        uia = [_el("u1", 5, 5, 100, 40)]
        ocr = [_el("o1", 5, 5, 100, 40, tier=PerceptionTier.OCR, confidence=0.7)]
        result = fuse_elements(uia, [], ocr)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "u1")

    def test_partial_overlap_below_threshold_added(self):
        """Two elements overlapping by less than IOU_THRESHOLD should both appear."""
        # 50×50 box at (0,0) and 50×50 box at (40,0) — small overlap
        uia    = [_el("u1", 0, 0, 50, 50)]
        vision = [_el("v1", 40, 0, 50, 50, tier=PerceptionTier.VISION, confidence=0.8)]
        result = fuse_elements(uia, vision)
        # IoU = (10×50)/(50×50+50×50-10×50) = 500/4500 ≈ 0.11 < 0.7
        self.assertEqual(len(result), 2)

    def test_high_overlap_vision_suppressed(self):
        """Elements with IoU ≥ 0.7 should be deduplicated (UIA wins)."""
        uia    = [_el("u1", 0, 0, 100, 100)]
        # 90×90 box at (5,5): intersection 90×90=8100, union=10000+8100-8100=10000 → IoU=0.81
        vision = [_el("v1", 5, 5, 90, 90, tier=PerceptionTier.VISION, confidence=0.9)]
        result = fuse_elements(uia, vision)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "u1")

    def test_vision_ocr_overlap_vision_wins(self):
        """When vision and OCR overlap, vision (higher tier) wins."""
        vision = [_el("v1", 0, 0, 100, 50, tier=PerceptionTier.VISION, confidence=0.8)]
        ocr    = [_el("o1", 0, 0, 100, 50, tier=PerceptionTier.OCR,    confidence=0.7)]
        result = fuse_elements([], vision, ocr)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "v1")


class TestFuseElementsSorting(unittest.TestCase):
    def test_sorted_by_confidence_descending(self):
        uia    = [_el("u1", 0,   0, 50, 50, confidence=1.0)]
        vision = [_el("v1", 200, 0, 50, 50, tier=PerceptionTier.VISION, confidence=0.5)]
        ocr    = [_el("o1", 400, 0, 50, 50, tier=PerceptionTier.OCR,    confidence=0.7)]
        result = fuse_elements(uia, vision, ocr)
        confs = [e.confidence for e in result]
        self.assertEqual(confs, sorted(confs, reverse=True))

    def test_low_confidence_uia_still_present(self):
        """Even a low-confidence UIA element is never discarded."""
        uia = [_el("u1", 0, 0, 50, 50, confidence=0.1)]
        result = fuse_elements(uia)
        self.assertEqual(len(result), 1)


class TestFuseElementsConfidenceCap(unittest.TestCase):
    def test_vision_confidence_capped_at_0_95(self):
        vision = [_el("v1", 0, 0, 50, 50, tier=PerceptionTier.VISION, confidence=0.99)]
        result = fuse_elements([], vision)
        self.assertLessEqual(result[0].confidence, 0.95)

    def test_ocr_confidence_capped_at_0_85(self):
        ocr = [_el("o1", 0, 0, 50, 50, tier=PerceptionTier.OCR, confidence=0.99)]
        result = fuse_elements([], [], ocr)
        self.assertLessEqual(result[0].confidence, 0.85)

    def test_below_cap_confidence_unchanged(self):
        vision = [_el("v1", 0, 0, 50, 50, tier=PerceptionTier.VISION, confidence=0.6)]
        result = fuse_elements([], vision)
        self.assertAlmostEqual(result[0].confidence, 0.6)

    def test_uia_confidence_not_capped(self):
        uia = [_el("u1", 0, 0, 50, 50, confidence=1.0)]
        result = fuse_elements(uia)
        self.assertAlmostEqual(result[0].confidence, 1.0)


class TestFuseElementsCustomThreshold(unittest.TestCase):
    def test_custom_threshold_stricter(self):
        """With threshold=0.1, even a small overlap suppresses the duplicate."""
        uia    = [_el("u1", 0, 0, 50, 50)]
        vision = [_el("v1", 40, 0, 50, 50, tier=PerceptionTier.VISION)]
        # Default threshold=0.7 → both kept; threshold=0.1 → vision suppressed
        result_default = fuse_elements(uia, vision, iou_threshold=0.7)
        result_strict  = fuse_elements(uia, vision, iou_threshold=0.1)
        self.assertEqual(len(result_default), 2)
        self.assertEqual(len(result_strict),  1)


if __name__ == "__main__":
    unittest.main()
