# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Unit tests for engine.router.api_adapters.

Tests run without external services — file/clipboard/web calls are mocked
or performed on temp files/strings.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from engine.types import Action, ActionType
from engine.router.api_adapters import (
    FileAdapter, ClipboardAdapter, WebAdapter,
    file_adapter, clipboard_adapter, web_adapter,
)


# ---------------------------------------------------------------------------
# FileAdapter
# ---------------------------------------------------------------------------

class TestFileAdapterReadWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".txt")
        self.adapter = FileAdapter()

    def tearDown(self):
        if os.path.exists(self.tmp):
            os.remove(self.tmp)

    def test_write_then_read(self):
        wr = self.adapter.write_file(self.tmp, "hello world")
        self.assertTrue(wr.success)
        rd = self.adapter.read_file(self.tmp)
        self.assertTrue(rd.success)
        self.assertEqual(rd.output, "hello world")

    def test_read_nonexistent_fails(self):
        result = self.adapter.read_file("/nonexistent/path/file.txt")
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

    def test_file_exists_true(self):
        self.adapter.write_file(self.tmp, "x")
        result = self.adapter.file_exists(self.tmp)
        self.assertTrue(result.success)
        self.assertEqual(result.output, "True")

    def test_file_exists_false(self):
        result = self.adapter.file_exists("/nonexistent/path.txt")
        self.assertTrue(result.success)
        self.assertEqual(result.output, "False")

    def test_delete_file(self):
        self.adapter.write_file(self.tmp, "data")
        result = self.adapter.delete_file(self.tmp)
        self.assertTrue(result.success)
        self.assertFalse(os.path.exists(self.tmp))

    def test_delete_nonexistent_fails(self):
        result = self.adapter.delete_file("/nonexistent/file.txt")
        self.assertFalse(result.success)

    def test_copy_file(self):
        dst = self.tmp + ".copy"
        try:
            self.adapter.write_file(self.tmp, "copy me")
            result = self.adapter.copy_file(self.tmp, dst)
            self.assertTrue(result.success)
            self.assertTrue(os.path.exists(dst))
        finally:
            if os.path.exists(dst):
                os.remove(dst)

    def test_move_file(self):
        dst = self.tmp + ".moved"
        try:
            self.adapter.write_file(self.tmp, "move me")
            result = self.adapter.move_file(self.tmp, dst)
            self.assertTrue(result.success)
            self.assertFalse(os.path.exists(self.tmp))
            self.assertTrue(os.path.exists(dst))
        finally:
            if os.path.exists(dst):
                os.remove(dst)


class TestFileAdapterCanHandle(unittest.TestCase):
    def setUp(self):
        self.adapter = FileAdapter()

    def test_read_action_can_handle(self):
        action = Action(action_type=ActionType.READ, element_id="C:/Users/test.txt")
        self.assertTrue(self.adapter.can_handle(action))

    def test_type_to_path_can_handle(self):
        action = Action(action_type=ActionType.TYPE, element_id="C:/some/path.txt", text="content")
        self.assertTrue(self.adapter.can_handle(action))

    def test_type_to_button_id_cannot_handle(self):
        action = Action(action_type=ActionType.TYPE, element_id="btn_001", text="hello")
        self.assertFalse(self.adapter.can_handle(action))

    def test_click_action_cannot_handle(self):
        action = Action(action_type=ActionType.CLICK, element_id="C:/file.txt")
        self.assertFalse(self.adapter.can_handle(action))


# ---------------------------------------------------------------------------
# ClipboardAdapter
# ---------------------------------------------------------------------------

class TestClipboardAdapterCanHandle(unittest.TestCase):
    def setUp(self):
        self.adapter = ClipboardAdapter()

    def test_clipboard_element_id_can_handle(self):
        action = Action(action_type=ActionType.READ, element_id="__clipboard__")
        self.assertTrue(self.adapter.can_handle(action))

    def test_clipboard_prefix_can_handle(self):
        action = Action(action_type=ActionType.TYPE, element_id="clipboard_text", text="hi")
        self.assertTrue(self.adapter.can_handle(action))

    def test_regular_element_cannot_handle(self):
        action = Action(action_type=ActionType.READ, element_id="btn_001")
        self.assertFalse(self.adapter.can_handle(action))


class TestClipboardAdapterMocked(unittest.TestCase):
    def setUp(self):
        self.adapter = ClipboardAdapter()

    def test_get_clipboard_uses_win32_if_available(self):
        mock_win32 = MagicMock()
        mock_win32.CF_UNICODETEXT = 13
        mock_win32.GetClipboardData.return_value = "from clipboard"

        with patch.dict("sys.modules", {"win32clipboard": mock_win32}):
            result = self.adapter.get_clipboard()

        self.assertTrue(result.success)
        self.assertEqual(result.output, "from clipboard")

    def test_set_clipboard_uses_win32_if_available(self):
        mock_win32 = MagicMock()
        mock_win32.CF_UNICODETEXT = 13

        with patch.dict("sys.modules", {"win32clipboard": mock_win32}):
            result = self.adapter.set_clipboard("test text")

        self.assertTrue(result.success)

    def test_get_clipboard_falls_back_to_pyperclip(self):
        import sys
        # Simulate win32clipboard import failure then pyperclip success
        mock_pyperclip = MagicMock()
        mock_pyperclip.paste.return_value = "pyperclip text"

        original = sys.modules.get("win32clipboard")
        sys.modules["win32clipboard"] = None  # type: ignore[assignment]
        try:
            with patch.dict("sys.modules", {"pyperclip": mock_pyperclip}):
                result = self.adapter.get_clipboard()
            self.assertTrue(result.success)
        finally:
            if original is None:
                sys.modules.pop("win32clipboard", None)
            else:
                sys.modules["win32clipboard"] = original

    def test_get_clipboard_returns_failure_when_all_fail(self):
        import sys
        original = sys.modules.get("win32clipboard")
        original_pp = sys.modules.get("pyperclip")
        sys.modules["win32clipboard"] = None  # type: ignore[assignment]
        sys.modules["pyperclip"] = None       # type: ignore[assignment]
        try:
            result = self.adapter.get_clipboard()
            self.assertFalse(result.success)
        finally:
            if original is None:
                sys.modules.pop("win32clipboard", None)
            else:
                sys.modules["win32clipboard"] = original
            if original_pp is None:
                sys.modules.pop("pyperclip", None)
            else:
                sys.modules["pyperclip"] = original_pp


# ---------------------------------------------------------------------------
# WebAdapter
# ---------------------------------------------------------------------------

class TestWebAdapterCanHandle(unittest.TestCase):
    def setUp(self):
        self.adapter = WebAdapter()

    def test_http_url_can_handle(self):
        action = Action(action_type=ActionType.READ, element_id="http://example.com")
        self.assertTrue(self.adapter.can_handle(action))

    def test_https_url_can_handle(self):
        action = Action(action_type=ActionType.TYPE, element_id="https://api.example.com", text="{}")
        self.assertTrue(self.adapter.can_handle(action))

    def test_non_url_cannot_handle(self):
        action = Action(action_type=ActionType.READ, element_id="btn_submit")
        self.assertFalse(self.adapter.can_handle(action))


class TestWebAdapterMocked(unittest.TestCase):
    def setUp(self):
        self.adapter = WebAdapter()

    def test_http_get_uses_httpx(self):
        mock_httpx = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "<html>ok</html>"
        mock_httpx.get.return_value = mock_resp

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = self.adapter.http_get("https://example.com")

        self.assertTrue(result.success)
        self.assertIn("ok", result.output)

    def test_http_get_falls_back_to_requests(self):
        import sys
        mock_requests = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "requests response"
        mock_requests.get.return_value = mock_resp

        original = sys.modules.get("httpx")
        sys.modules["httpx"] = None  # type: ignore[assignment]
        try:
            with patch.dict("sys.modules", {"requests": mock_requests}):
                result = self.adapter.http_get("https://example.com")
            self.assertTrue(result.success)
            self.assertEqual(result.output, "requests response")
        finally:
            if original is None:
                sys.modules.pop("httpx", None)
            else:
                sys.modules["httpx"] = original

    def test_http_get_fails_when_no_client(self):
        import sys
        orig_httpx = sys.modules.get("httpx")
        orig_req   = sys.modules.get("requests")
        sys.modules["httpx"]    = None  # type: ignore[assignment]
        sys.modules["requests"] = None  # type: ignore[assignment]
        try:
            result = self.adapter.http_get("https://example.com")
            self.assertFalse(result.success)
        finally:
            if orig_httpx is None: sys.modules.pop("httpx", None)
            else: sys.modules["httpx"] = orig_httpx
            if orig_req is None: sys.modules.pop("requests", None)
            else: sys.modules["requests"] = orig_req

    def test_http_post_mocked(self):
        mock_httpx = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '{"status":"ok"}'
        mock_httpx.post.return_value = mock_resp

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = self.adapter.http_post("https://api.example.com", '{"key":"val"}')

        self.assertTrue(result.success)
        self.assertIn("ok", result.output)


# ---------------------------------------------------------------------------
# Singleton sanity
# ---------------------------------------------------------------------------

class TestSingletons(unittest.TestCase):
    def test_file_adapter_is_file_adapter(self):
        self.assertIsInstance(file_adapter, FileAdapter)

    def test_clipboard_adapter_is_clipboard_adapter(self):
        self.assertIsInstance(clipboard_adapter, ClipboardAdapter)

    def test_web_adapter_is_web_adapter(self):
        self.assertIsInstance(web_adapter, WebAdapter)


if __name__ == "__main__":
    unittest.main()
