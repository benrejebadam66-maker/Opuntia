# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Unit tests for engine.perception.ocr.

All tests run without a real Tesseract installation — we verify stub behaviour:
- extract_text_elements(None) → []
- extract_text_elements(frame) → [] when pytesseract not present, no crash
- With mocked pytesseract, returns correct Element list
"""

import unittest
from unittest.mock import MagicMock, patch

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

from engine.perception.ocr import extract_text_elements


class TestExtractTextElementsStub(unittest.TestCase):
    """Tests that run without pytesseract installed."""

    def test_none_frame_returns_empty(self):
        result = extract_text_elements(None)
        self.assertEqual(result, [])

    def test_returns_list_type(self):
        result = extract_text_elements(None)
        self.assertIsInstance(result, list)

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_no_tesseract_returns_empty_no_crash(self):
        """When pytesseract absent, gracefully returns []."""
        import engine.perception.ocr as ocr_module
        original = ocr_module._TESSERACT_AVAILABLE
        try:
            ocr_module._TESSERACT_AVAILABLE = False
            ocr_module._TESSERACT_WARNING_ISSUED = False
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            result = extract_text_elements(frame)
            self.assertEqual(result, [])
        finally:
            ocr_module._TESSERACT_AVAILABLE = original

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_no_numpy_returns_empty(self):
        """When numpy absent, gracefully returns []."""
        import engine.perception.ocr as ocr_module
        original_tess = ocr_module._TESSERACT_AVAILABLE
        original_np = ocr_module._NUMPY_AVAILABLE
        try:
            ocr_module._TESSERACT_AVAILABLE = True
            ocr_module._NUMPY_AVAILABLE = False
            frame = np.zeros((50, 50, 3), dtype=np.uint8)
            result = extract_text_elements(frame)
            self.assertEqual(result, [])
        finally:
            ocr_module._TESSERACT_AVAILABLE = original_tess
            ocr_module._NUMPY_AVAILABLE = original_np


class TestExtractTextElementsMocked(unittest.TestCase):
    """Tests using a mocked pytesseract to exercise the parsing logic."""

    def _make_tess_data(self, texts, confs, lefts, tops, widths, heights):
        return {
            "text": texts,
            "conf": confs,
            "left": lefts,
            "top": tops,
            "width": widths,
            "height": heights,
        }

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_mocked_single_word_returns_one_element(self):
        import engine.perception.ocr as ocr_module
        original_tess = ocr_module._TESSERACT_AVAILABLE
        try:
            ocr_module._TESSERACT_AVAILABLE = True

            mock_pt = MagicMock()
            mock_pt.Output.DICT = "dict"
            mock_pt.image_to_data.return_value = self._make_tess_data(
                texts=["Hello"],
                confs=[90.0],
                lefts=[10], tops=[20], widths=[50], heights=[15],
            )

            with patch.object(ocr_module, "pytesseract", mock_pt):
                frame = np.zeros((100, 100, 3), dtype=np.uint8)
                result = extract_text_elements(frame)

            self.assertEqual(len(result), 1)
            el = result[0]
            self.assertEqual(el.label, "Hello")
            self.assertEqual(el.control_type, "Text")
            self.assertAlmostEqual(el.confidence, 0.9)
            self.assertEqual(el.id, "ocr_000")
        finally:
            ocr_module._TESSERACT_AVAILABLE = original_tess

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_low_confidence_word_excluded(self):
        import engine.perception.ocr as ocr_module
        original_tess = ocr_module._TESSERACT_AVAILABLE
        try:
            ocr_module._TESSERACT_AVAILABLE = True

            mock_pt = MagicMock()
            mock_pt.Output.DICT = "dict"
            mock_pt.image_to_data.return_value = self._make_tess_data(
                texts=["BadWord", "GoodWord"],
                confs=[30.0, 85.0],   # 30 < min_confidence=60
                lefts=[0, 60], tops=[0, 0], widths=[50, 50], heights=[15, 15],
            )

            with patch.object(ocr_module, "pytesseract", mock_pt):
                frame = np.zeros((100, 100, 3), dtype=np.uint8)
                result = extract_text_elements(frame, min_confidence=60.0)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].label, "GoodWord")
        finally:
            ocr_module._TESSERACT_AVAILABLE = original_tess

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_short_text_excluded(self):
        import engine.perception.ocr as ocr_module
        original_tess = ocr_module._TESSERACT_AVAILABLE
        try:
            ocr_module._TESSERACT_AVAILABLE = True

            mock_pt = MagicMock()
            mock_pt.Output.DICT = "dict"
            mock_pt.image_to_data.return_value = self._make_tess_data(
                texts=["A", "OK"],  # "A" len=1 < min_text_len=2
                confs=[95.0, 95.0],
                lefts=[0, 10], tops=[0, 0], widths=[10, 20], heights=[10, 10],
            )

            with patch.object(ocr_module, "pytesseract", mock_pt):
                frame = np.zeros((100, 100, 3), dtype=np.uint8)
                result = extract_text_elements(frame, min_text_len=2)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].label, "OK")
        finally:
            ocr_module._TESSERACT_AVAILABLE = original_tess

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_zero_size_box_excluded(self):
        import engine.perception.ocr as ocr_module
        original_tess = ocr_module._TESSERACT_AVAILABLE
        try:
            ocr_module._TESSERACT_AVAILABLE = True

            mock_pt = MagicMock()
            mock_pt.Output.DICT = "dict"
            mock_pt.image_to_data.return_value = self._make_tess_data(
                texts=["Word"],
                confs=[90.0],
                lefts=[10], tops=[10], widths=[0], heights=[0],  # zero area
            )

            with patch.object(ocr_module, "pytesseract", mock_pt):
                frame = np.zeros((100, 100, 3), dtype=np.uint8)
                result = extract_text_elements(frame)

            self.assertEqual(result, [])
        finally:
            ocr_module._TESSERACT_AVAILABLE = original_tess

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_element_has_ocr_source_tier(self):
        import engine.perception.ocr as ocr_module
        from engine.types import PerceptionTier
        original_tess = ocr_module._TESSERACT_AVAILABLE
        try:
            ocr_module._TESSERACT_AVAILABLE = True

            mock_pt = MagicMock()
            mock_pt.Output.DICT = "dict"
            mock_pt.image_to_data.return_value = self._make_tess_data(
                texts=["Submit"],
                confs=[88.0],
                lefts=[5], tops=[5], widths=[40], heights=[12],
            )

            with patch.object(ocr_module, "pytesseract", mock_pt):
                frame = np.zeros((100, 100, 3), dtype=np.uint8)
                result = extract_text_elements(frame)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].source_tier, PerceptionTier.OCR)
        finally:
            ocr_module._TESSERACT_AVAILABLE = original_tess

    @unittest.skipUnless(_NUMPY, "numpy not installed")
    def test_multiple_elements_sequential_ids(self):
        import engine.perception.ocr as ocr_module
        original_tess = ocr_module._TESSERACT_AVAILABLE
        try:
            ocr_module._TESSERACT_AVAILABLE = True

            mock_pt = MagicMock()
            mock_pt.Output.DICT = "dict"
            mock_pt.image_to_data.return_value = self._make_tess_data(
                texts=["First", "Second", "Third"],
                confs=[80.0, 85.0, 90.0],
                lefts=[0, 60, 120], tops=[0, 0, 0],
                widths=[50, 50, 50], heights=[12, 12, 12],
            )

            with patch.object(ocr_module, "pytesseract", mock_pt):
                frame = np.zeros((100, 200, 3), dtype=np.uint8)
                result = extract_text_elements(frame)

            self.assertEqual(len(result), 3)
            self.assertEqual(result[0].id, "ocr_000")
            self.assertEqual(result[1].id, "ocr_001")
            self.assertEqual(result[2].id, "ocr_002")
        finally:
            ocr_module._TESSERACT_AVAILABLE = original_tess


if __name__ == "__main__":
    unittest.main()
