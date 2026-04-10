# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Native API adapters — bypass UI automation for file, clipboard, and web
operations that can be performed directly through OS/stdlib APIs.

Each adapter exposes:
    can_handle(action) -> bool
    execute(action)    -> ActionResult

Adapters are checked before MCP and UIA to keep operations fast and reliable.

Available adapters
------------------
FileAdapter       — read / write / copy / move / delete via os / shutil
ClipboardAdapter  — get / set clipboard text via win32clipboard or pyperclip
WebAdapter        — HTTP GET / POST via httpx (async) or requests (sync)
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Optional

from engine.types import Action, ActionResult, ActionType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class BaseAdapter:
    """Abstract base for all native API adapters."""

    def can_handle(self, action: Action) -> bool:
        """Return True if this adapter can execute *action*."""
        raise NotImplementedError

    def execute(self, action: Action) -> ActionResult:
        """Execute *action* and return the result."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# File adapter
# ---------------------------------------------------------------------------

class FileAdapter(BaseAdapter):
    """
    Handles file-system actions using os / shutil.

    Supported action_type values (stored in Action.text as a sub-command):
        "read"   — read file at element_id path, return content in output
        "write"  — write Action.text to element_id path
        "copy"   — copy element_id → Action.text (dest path)
        "move"   — move element_id → Action.text
        "delete" — delete file at element_id path
        "exists" — check whether element_id path exists

    Convention: element_id is used as the source path; Action.text as
    secondary argument (dest path for copy/move, content for write).
    """

    _FILE_SUBTYPES = frozenset({"read", "write", "copy", "move", "delete", "exists"})

    def can_handle(self, action: Action) -> bool:
        return (
            action.action_type == ActionType.READ
            or (
                action.action_type == ActionType.TYPE
                and action.text is not None
                and action.element_id is not None
                and _looks_like_path(action.element_id)
            )
        )

    def execute(self, action: Action) -> ActionResult:
        try:
            if action.action_type == ActionType.READ:
                return self._read(action)
            if action.action_type == ActionType.TYPE:
                return self._write(action)
            return ActionResult(
                success=False,
                error=f"FileAdapter: unsupported action_type {action.action_type}",
            )
        except Exception as exc:
            logger.error("FileAdapter.execute error: %s", exc)
            return ActionResult(success=False, error=str(exc))

    # -- sub-operations --

    def read_file(self, path: str) -> ActionResult:
        """Read text content from *path*."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            return ActionResult(success=True, output=content, method_used="file_read")
        except OSError as exc:
            return ActionResult(success=False, error=str(exc))

    def write_file(self, path: str, content: str) -> ActionResult:
        """Write *content* to *path* (creates parent dirs if needed)."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            return ActionResult(success=True, method_used="file_write")
        except OSError as exc:
            return ActionResult(success=False, error=str(exc))

    def copy_file(self, src: str, dst: str) -> ActionResult:
        try:
            shutil.copy2(src, dst)
            return ActionResult(success=True, method_used="file_copy")
        except OSError as exc:
            return ActionResult(success=False, error=str(exc))

    def move_file(self, src: str, dst: str) -> ActionResult:
        try:
            shutil.move(src, dst)
            return ActionResult(success=True, method_used="file_move")
        except OSError as exc:
            return ActionResult(success=False, error=str(exc))

    def delete_file(self, path: str) -> ActionResult:
        try:
            os.remove(path)
            return ActionResult(success=True, method_used="file_delete")
        except OSError as exc:
            return ActionResult(success=False, error=str(exc))

    def file_exists(self, path: str) -> ActionResult:
        exists = os.path.exists(path)
        return ActionResult(
            success=True,
            output=str(exists),
            method_used="file_exists",
        )

    # -- internal dispatch --

    def _read(self, action: Action) -> ActionResult:
        path = action.element_id or ""
        return self.read_file(path)

    def _write(self, action: Action) -> ActionResult:
        path    = action.element_id or ""
        content = action.text or ""
        return self.write_file(path, content)


# ---------------------------------------------------------------------------
# Clipboard adapter
# ---------------------------------------------------------------------------

class ClipboardAdapter(BaseAdapter):
    """
    Handles clipboard get/set operations.

    Tries win32clipboard first (Windows-native, no extra install on most
    Windows Python envs), then falls back to pyperclip.

    Convention:
        ActionType.READ  → get clipboard text (element_id ignored)
        ActionType.TYPE  → set clipboard text to action.text
    """

    def can_handle(self, action: Action) -> bool:
        return action.action_type in (ActionType.READ, ActionType.TYPE) and (
            action.element_id == "__clipboard__"
            or (action.element_id or "").lower().startswith("clipboard")
        )

    def execute(self, action: Action) -> ActionResult:
        try:
            if action.action_type == ActionType.READ:
                return self.get_clipboard()
            if action.action_type == ActionType.TYPE:
                return self.set_clipboard(action.text or "")
            return ActionResult(
                success=False,
                error=f"ClipboardAdapter: unsupported action_type {action.action_type}",
            )
        except Exception as exc:
            logger.error("ClipboardAdapter.execute error: %s", exc)
            return ActionResult(success=False, error=str(exc))

    def get_clipboard(self) -> ActionResult:
        """Return the current clipboard text."""
        text = self._get_text()
        if text is None:
            return ActionResult(success=False, error="Clipboard read failed")
        return ActionResult(success=True, output=text, method_used="clipboard_get")

    def set_clipboard(self, text: str) -> ActionResult:
        """Set clipboard to *text*."""
        ok = self._set_text(text)
        if not ok:
            return ActionResult(success=False, error="Clipboard write failed")
        return ActionResult(success=True, method_used="clipboard_set")

    # -- platform helpers --

    def _get_text(self) -> Optional[str]:
        try:
            import win32clipboard  # type: ignore[import]
            win32clipboard.OpenClipboard()
            try:
                return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass
        try:
            import pyperclip  # type: ignore[import]
            return pyperclip.paste()
        except Exception:
            pass
        return None

    def _set_text(self, text: str) -> bool:
        try:
            import win32clipboard  # type: ignore[import]
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception:
            pass
        try:
            import pyperclip  # type: ignore[import]
            pyperclip.copy(text)
            return True
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Web adapter
# ---------------------------------------------------------------------------

class WebAdapter(BaseAdapter):
    """
    Handles simple HTTP GET / POST actions.

    Convention:
        ActionType.READ  → HTTP GET  to element_id (treated as URL)
        ActionType.TYPE  → HTTP POST to element_id with action.text as body
    """

    def can_handle(self, action: Action) -> bool:
        return action.action_type in (ActionType.READ, ActionType.TYPE) and (
            action.element_id or ""
        ).startswith(("http://", "https://"))

    def execute(self, action: Action) -> ActionResult:
        try:
            if action.action_type == ActionType.READ:
                return self.http_get(action.element_id or "")
            if action.action_type == ActionType.TYPE:
                return self.http_post(action.element_id or "", action.text or "")
            return ActionResult(
                success=False,
                error=f"WebAdapter: unsupported action_type {action.action_type}",
            )
        except Exception as exc:
            logger.error("WebAdapter.execute error: %s", exc)
            return ActionResult(success=False, error=str(exc))

    def http_get(self, url: str, timeout: float = 10.0) -> ActionResult:
        text = self._get(url, timeout)
        if text is None:
            return ActionResult(success=False, error=f"HTTP GET failed: {url}")
        return ActionResult(success=True, output=text, method_used="web_get")

    def http_post(self, url: str, body: str, timeout: float = 10.0) -> ActionResult:
        text = self._post(url, body, timeout)
        if text is None:
            return ActionResult(success=False, error=f"HTTP POST failed: {url}")
        return ActionResult(success=True, output=text, method_used="web_post")

    # -- http helpers --

    def _get(self, url: str, timeout: float) -> Optional[str]:
        try:
            import httpx  # type: ignore[import]
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception:
            pass
        try:
            import requests  # type: ignore[import]
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception:
            pass
        return None

    def _post(self, url: str, body: str, timeout: float) -> Optional[str]:
        try:
            import httpx  # type: ignore[import]
            resp = httpx.post(url, content=body, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception:
            pass
        try:
            import requests  # type: ignore[import]
            resp = requests.post(url, data=body, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _looks_like_path(s: str) -> bool:
    """Heuristic: does this string look like a file-system path?"""
    return (
        os.sep in s
        or s.startswith("/")
        or (len(s) >= 3 and s[1] == ":" and s[2] in ("/", "\\"))
    )


# Singleton instances for the router to import directly
file_adapter      = FileAdapter()
clipboard_adapter = ClipboardAdapter()
web_adapter       = WebAdapter()

__all__ = [
    "BaseAdapter",
    "FileAdapter",
    "ClipboardAdapter",
    "WebAdapter",
    "file_adapter",
    "clipboard_adapter",
    "web_adapter",
]
