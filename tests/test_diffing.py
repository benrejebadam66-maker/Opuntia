# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Unit tests for engine.perception.diffing.

Tests run without a real screen — we construct synthetic numpy arrays.
"""

import unittest

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

from engine.perception.diffing import (
    compute_frame_hash,
    is_frame_unchanged,
    hamming_distance,
)


class TestComputeFrameHash(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(compute_frame_hash(None))

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_identical_frames_same_hash(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        h1 = compute_frame_hash(frame)
        h2 = compute_frame_hash(frame)
        self.assertIsNotNone(h1)
        self.assertEqual(h1, h2)

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_different_frames_different_hash(self):
        frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
        frame2 = np.full((100, 100, 3), 255, dtype=np.uint8)
        h1 = compute_frame_hash(frame1)
        h2 = compute_frame_hash(frame2)
        self.assertNotEqual(h1, h2)

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_returns_hex_string(self):
        frame = np.ones((50, 50, 3), dtype=np.uint8) * 128
        h = compute_frame_hash(frame)
        self.assertIsNotNone(h)
        # Must be a valid hex string
        int(h, 16)


class TestIsFrameUnchanged(unittest.TestCase):
    def test_no_prev_hash_returns_changed(self):
        unchanged, ratio = is_frame_unchanged(None, None)
        self.assertFalse(unchanged)
        self.assertAlmostEqual(ratio, 1.0)

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_identical_frame_unchanged(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        h = compute_frame_hash(frame)
        unchanged, ratio = is_frame_unchanged(frame, h)
        self.assertTrue(unchanged)
        self.assertAlmostEqual(ratio, 0.0)

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_totally_different_frame_changed(self):
        frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
        frame2 = np.full((100, 100, 3), 255, dtype=np.uint8)
        h1 = compute_frame_hash(frame1)
        unchanged, ratio = is_frame_unchanged(frame2, h1)
        self.assertFalse(unchanged)
        self.assertGreater(ratio, 0.0)

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_slightly_different_frame_respects_threshold(self):
        # A mostly-black frame with one bright pixel — should be "unchanged"
        # at the default 5% threshold since very few hash bits flip
        frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
        frame2 = frame1.copy()
        frame2[50, 50] = [255, 255, 255]  # single pixel change
        h1 = compute_frame_hash(frame1)
        unchanged, ratio = is_frame_unchanged(frame2, h1, threshold=0.5)
        # With generous threshold, tiny change → unchanged
        self.assertTrue(unchanged)


class TestHammingDistance(unittest.TestCase):
    def test_same_hash_zero_distance(self):
        self.assertEqual(hamming_distance("ff", "ff"), 0)

    def test_all_chars_different(self):
        # "00" vs "ff" — both characters differ → distance 2
        self.assertEqual(hamming_distance("00", "ff"), 2)

    def test_one_char_different(self):
        self.assertEqual(hamming_distance("0f", "ff"), 1)

    def test_invalid_hex_returns_large(self):
        dist = hamming_distance("zz", "ff")
        self.assertGreater(dist, 1000)


if __name__ == "__main__":
    unittest.main()
