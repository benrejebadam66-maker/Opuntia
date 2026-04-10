# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Unit tests for engine.perception.vision.

All tests run without a real ONNX model — we verify the stub behaviour:
- detect_ui_elements(None) → []
- detect_ui_elements(frame) → [] when model not present, no crash
- is_model_available() → False when model file absent
"""

import unittest

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

from engine.perception.vision import detect_ui_elements, is_model_available


class TestVisionStub(unittest.TestCase):
    """Tests that run without an ONNX model file."""

    def test_none_frame_returns_empty(self):
        result = detect_ui_elements(None)
        self.assertEqual(result, [])

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_no_model_returns_empty_no_crash(self):
        """When model file is absent, stub returns [] gracefully."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Pass a non-existent model path to force stub mode
        result = detect_ui_elements(frame, model_path="/nonexistent/model.onnx")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_is_model_available_false_for_nonexistent_path(self):
        available = is_model_available("/nonexistent/model.onnx")
        self.assertFalse(available)

    def test_is_model_available_returns_bool(self):
        result = is_model_available()
        self.assertIsInstance(result, bool)

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_returns_list_type(self):
        frame = np.ones((100, 100, 3), dtype=np.uint8) * 128
        result = detect_ui_elements(frame, model_path="/nonexistent/model.onnx")
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
