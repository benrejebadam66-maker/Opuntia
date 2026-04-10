# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Hybrid action router — selects the best execution path for each action.

Priority
--------
1. Native API adapter (FileAdapter / ClipboardAdapter / WebAdapter)
   — fastest, most reliable for OS-level operations
2. MCP bridge — for actions routed through a model-context-protocol server
3. UIA pattern — Windows UI Automation (InvokePattern, ValuePattern, …)
4. SendInput fallback — coordinate-based mouse/keyboard emulation

The router never raises; it returns an ActionResult with success=False and
an error string when all paths are exhausted.

Usage
-----
    from engine.router.routing import route_action
    from engine.types import Action, ActionType

    result = route_action(Action(ActionType.CLICK, element_id="btn_ok"),
                          element_map=my_element_map)
"""

from __future__ import annotations

import logging
from typing import Optional

from engine.types import Action, ActionResult, ActionType, ElementMap

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def route_action(
    action: Action,
    element_map: Optional[ElementMap] = None,
) -> ActionResult:
    """
    Route an action through the priority chain and return the first success.

    Parameters
    ----------
    action : Action
        The action to execute.
    element_map : ElementMap, optional
        Current element snapshot — used to look up element metadata when
        the UIA path needs bounding-box / control-type info.

    Returns
    -------
    ActionResult
        Result from whichever path succeeded, or a failure result if all
        paths were exhausted.
    """
    # 1. Native API adapters
    result = _try_api_adapters(action)
    if result is not None and result.success:
        logger.debug("route_action: API adapter succeeded (%s)", result.method_used)
        return result

    # 2. MCP bridge
    result = _try_mcp(action)
    if result is not None and result.success:
        logger.debug("route_action: MCP bridge succeeded (%s)", result.method_used)
        return result

    # 3. UIA execution
    result = _try_uia(action, element_map)
    if result is not None and result.success:
        logger.debug("route_action: UIA pattern succeeded (%s)", result.method_used)
        return result

    # 4. SendInput fallback
    result = _try_sendinput(action, element_map)
    if result is not None and result.success:
        logger.debug("route_action: SendInput fallback succeeded")
        return result

    # All paths exhausted
    reasons = [
        r.error for r in [result] if r is not None and r.error
    ]
    error_msg = reasons[0] if reasons else "All execution paths failed"
    logger.warning("route_action: all paths failed for %s — %s", action.action_type, error_msg)
    return ActionResult(success=False, error=error_msg)


# ---------------------------------------------------------------------------
# Path 1: Native API adapters
# ---------------------------------------------------------------------------

def _try_api_adapters(action: Action) -> Optional[ActionResult]:
    try:
        from engine.router.api_adapters import (
            file_adapter, clipboard_adapter, web_adapter
        )
        for adapter in (file_adapter, clipboard_adapter, web_adapter):
            try:
                if adapter.can_handle(action):
                    return adapter.execute(action)
            except Exception as exc:
                logger.debug("API adapter %s error: %s", type(adapter).__name__, exc)
    except Exception as exc:
        logger.debug("_try_api_adapters import error: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Path 2: MCP bridge
# ---------------------------------------------------------------------------

def _try_mcp(action: Action) -> Optional[ActionResult]:
    """Attempt execution via the MCP bridge (optional component)."""
    try:
        from agents.mcp_bridge import MCPBridge  # type: ignore[import]
        bridge = MCPBridge()
        if hasattr(bridge, "can_handle") and bridge.can_handle(action):
            result = bridge.execute(action)
            if result is not None:
                return result
    except Exception as exc:
        logger.debug("MCP bridge unavailable or failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Path 3: UIA execution
# ---------------------------------------------------------------------------

def _try_uia(
    action: Action,
    element_map: Optional[ElementMap],
) -> Optional[ActionResult]:
    """
    Delegate to the engine's existing UIA execution layer.
    Imports engine.execution.actions to reuse InvokePattern/ValuePattern logic.
    """
    try:
        import asyncio
        from engine.execution.actions import execute_action as _uia_execute
        # execute_action is async — run synchronously inside the router
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already inside an event loop — schedule as a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        asyncio.run,
                        _uia_execute(action, element_map),
                    )
                    return future.result(timeout=action.timeout_ms / 1000 + 1)
            else:
                return loop.run_until_complete(_uia_execute(action, element_map))
        except Exception as exc:
            logger.debug("UIA async execute error: %s", exc)
            return None
    except Exception as exc:
        logger.debug("_try_uia import/dispatch error: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Path 4: SendInput fallback
# ---------------------------------------------------------------------------

def _try_sendinput(
    action: Action,
    element_map: Optional[ElementMap],
) -> Optional[ActionResult]:
    """
    Last-resort coordinate-based execution via InputControlBridge / SendInput.
    Only meaningful for CLICK and TYPE actions with a known bounding box.
    """
    if action.action_type not in (ActionType.CLICK, ActionType.TYPE):
        return None

    # Resolve element bounding box
    el = None
    if element_map and action.element_id:
        el = element_map.by_id(action.element_id)

    if el is None:
        return None

    try:
        from engine.compat.input_control_bridge import InputControlBridge
        bridge = InputControlBridge()
        cx, cy = el.bbox.center

        if action.action_type == ActionType.CLICK:
            ok = bridge.click(cx, cy)
            return ActionResult(
                success=ok,
                method_used="sendinput_click",
                error=None if ok else "SendInput click failed",
            )

        if action.action_type == ActionType.TYPE:
            ok = bridge.type_text(action.text or "")
            return ActionResult(
                success=ok,
                method_used="sendinput_type",
                error=None if ok else "SendInput type failed",
            )
    except Exception as exc:
        logger.debug("_try_sendinput error: %s", exc)

    return None


__all__ = ["route_action"]
