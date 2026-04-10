# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Action execution engine — UIA-first with SendInput fallback.

Priority order for each action type:
  1. UIA pattern (InvokePattern, ValuePattern, etc.) — instant, reliable, no cursor movement
  2. SendInput via fallback_dispatcher — coordinate-based, works for anything

The fallback_dispatcher is the existing agents/input_control.py dispatcher
(or an InputControlBridge wrapping it).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from engine.types import Action, ActionResult, ActionType, Element, ElementMap

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UIA helpers — all wrapped in try/except so failures fall through to SendInput
# ---------------------------------------------------------------------------

def _uia_control_from_element(el: Element) -> Any:
    """Re-acquire the live UIA control for an element by its bounding rect + name."""
    try:
        import uiautomation as auto
        # Search by name + control type near the element's center
        cx, cy = el.bbox.center
        ctrl = auto.ControlFromPoint(cx, cy)
        if ctrl and (ctrl.Name or "").strip() == el.label:
            return ctrl
        # Fallback: search by name on the desktop
        ctrl = auto.FindControl(
            searchDepth=8,
            Name=el.label,
            ControlType=getattr(auto, f"{el.control_type}Control", None),
        )
        return ctrl
    except Exception:
        return None


async def _try_uia_invoke(el: Element) -> Optional[ActionResult]:
    """Try UIA InvokePattern.Invoke() — the cleanest way to click a button."""
    def _sync():
        try:
            import uiautomation as auto
            cx, cy = el.bbox.center
            ctrl = auto.ControlFromPoint(cx, cy)
            if ctrl is None:
                return None
            pattern = ctrl.GetPattern(ctrl.InvokePatternId)
            if pattern:
                pattern.Invoke()
                return ActionResult(success=True, method_used="uia_invoke")
        except Exception as exc:
            logger.debug("uia_invoke failed: %s", exc)
        return None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


async def _try_uia_set_value(el: Element, text: str) -> Optional[ActionResult]:
    """Try UIA ValuePattern.SetValue() — sets text without keystrokes."""
    def _sync():
        try:
            import uiautomation as auto
            cx, cy = el.bbox.center
            ctrl = auto.ControlFromPoint(cx, cy)
            if ctrl is None:
                return None
            pattern = ctrl.GetPattern(ctrl.ValuePatternId)
            if pattern and not pattern.IsReadOnly:
                pattern.SetValue(text)
                return ActionResult(success=True, method_used="uia_set_value", output=text)
        except Exception as exc:
            logger.debug("uia_set_value failed: %s", exc)
        return None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


async def _try_uia_get_value(el: Element) -> Optional[ActionResult]:
    """Try reading element value via ValuePattern or TextPattern."""
    def _sync():
        try:
            import uiautomation as auto
            cx, cy = el.bbox.center
            ctrl = auto.ControlFromPoint(cx, cy)
            if ctrl is None:
                return None
            # Try ValuePattern first
            vp = ctrl.GetPattern(ctrl.ValuePatternId)
            if vp:
                val = vp.Value
                if val is not None:
                    return ActionResult(success=True, method_used="uia_value_pattern", output=str(val))
            # Try TextPattern
            tp = ctrl.GetPattern(ctrl.TextPatternId)
            if tp:
                text = tp.DocumentRange.GetText(-1)
                return ActionResult(success=True, method_used="uia_text_pattern", output=text)
            # Fall back to Name property
            name = ctrl.Name or ""
            if name:
                return ActionResult(success=True, method_used="uia_name", output=name)
        except Exception as exc:
            logger.debug("uia_get_value failed: %s", exc)
        return None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


async def _try_uia_scroll(el: Element, amount: int) -> Optional[ActionResult]:
    """Try UIA ScrollPattern — amount > 0 scrolls down, < 0 up."""
    def _sync():
        try:
            import uiautomation as auto
            cx, cy = el.bbox.center
            ctrl = auto.ControlFromPoint(cx, cy)
            if ctrl is None:
                return None
            pattern = ctrl.GetPattern(ctrl.ScrollPatternId)
            if pattern:
                direction = auto.ScrollAmount.SmallIncrement if amount > 0 else auto.ScrollAmount.SmallDecrement
                for _ in range(abs(amount)):
                    pattern.Scroll(auto.ScrollAmount.NoAmount, direction)
                return ActionResult(success=True, method_used="uia_scroll")
        except Exception as exc:
            logger.debug("uia_scroll failed: %s", exc)
        return None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

async def execute_action(
    action: Action,
    element_map: Optional[ElementMap] = None,
    fallback_dispatcher: Optional[Any] = None,
    use_router: bool = True,
) -> ActionResult:
    """
    Execute an atomic action, preferring UIA patterns over raw injection.

    Parameters
    ----------
    action : Action
        The action to execute (type, target element ID, parameters).
    element_map : ElementMap, optional
        Current perception snapshot — used to resolve element_id → Element.
    fallback_dispatcher : optional
        The existing input_control dispatcher (or InputControlBridge).
        Used when UIA patterns are unavailable or fail.
    use_router : bool
        When True (default), first attempt execution via the hybrid router
        (API adapters → MCP → UIA → SendInput).  Set to False to bypass
        the router and use only the local UIA/SendInput logic.

    Returns
    -------
    ActionResult
        success, output, method_used, duration_ms.
    """
    t0 = time.monotonic()

    # --- Hybrid router (optional, default on) ---
    if use_router:
        try:
            from engine.router.routing import route_action
            result = route_action(action, element_map=element_map)
            if result.success:
                result.duration_ms = (time.monotonic() - t0) * 1000
                logger.info(
                    "execute_action %s → success via router/%s (%.1f ms)",
                    action.action_type.value, result.method_used, result.duration_ms,
                )
                return result
            # Router failed — fall through to legacy UIA path below
            logger.debug(
                "Router did not succeed for %s (%s) — falling through to UIA",
                action.action_type.value, result.error,
            )
        except Exception as exc:
            logger.debug("Router import/exec error: %s — falling through", exc)

    el: Optional[Element] = None
    if action.element_id and element_map is not None:
        el = element_map.by_id(action.element_id)
        if el is None:
            return ActionResult(
                success=False,
                error=f"Element '{action.element_id}' not found in ElementMap",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

    result: Optional[ActionResult] = None

    # ---- CLICK ----
    if action.action_type == ActionType.CLICK:
        if el is not None:
            result = await _try_uia_invoke(el)
        if result is None and el is not None and fallback_dispatcher is not None:
            cx, cy = el.bbox.center
            try:
                if asyncio.iscoroutinefunction(fallback_dispatcher.click):
                    result = await fallback_dispatcher.click(cx, cy)
                else:
                    fallback_dispatcher.click(cx, cy)
                    result = ActionResult(success=True, method_used="sendinput_fallback")
            except Exception as exc:
                result = ActionResult(success=False, error=str(exc), method_used="sendinput_fallback")

    # ---- TYPE ----
    elif action.action_type == ActionType.TYPE:
        text = action.text or ""
        if el is not None:
            result = await _try_uia_set_value(el, text)
        if result is None and el is not None and fallback_dispatcher is not None:
            cx, cy = el.bbox.center
            try:
                # Click first to focus
                if asyncio.iscoroutinefunction(fallback_dispatcher.click):
                    await fallback_dispatcher.click(cx, cy)
                else:
                    fallback_dispatcher.click(cx, cy)
                if asyncio.iscoroutinefunction(fallback_dispatcher.type_text):
                    result = await fallback_dispatcher.type_text(text)
                else:
                    fallback_dispatcher.type_text(text)
                    result = ActionResult(success=True, method_used="sendinput_fallback", output=text)
            except Exception as exc:
                result = ActionResult(success=False, error=str(exc), method_used="sendinput_fallback")

    # ---- READ ----
    elif action.action_type == ActionType.READ:
        if el is not None:
            result = await _try_uia_get_value(el)
        if result is None:
            result = ActionResult(
                success=False,
                error="Could not read element value",
                method_used="none",
            )

    # ---- SCROLL ----
    elif action.action_type == ActionType.SCROLL:
        amount = action.scroll_amount or 3
        if el is not None:
            result = await _try_uia_scroll(el, amount)
        if result is None and fallback_dispatcher is not None:
            try:
                target_x, target_y = (el.bbox.center if el else (960, 540))
                if asyncio.iscoroutinefunction(fallback_dispatcher.scroll):
                    result = await fallback_dispatcher.scroll(target_x, target_y, amount)
                else:
                    fallback_dispatcher.scroll(target_x, target_y, amount)
                    result = ActionResult(success=True, method_used="sendinput_fallback")
            except Exception as exc:
                result = ActionResult(success=False, error=str(exc), method_used="sendinput_fallback")

    # ---- HOTKEY ----
    elif action.action_type == ActionType.HOTKEY:
        # No UIA equivalent — always uses SendInput
        keys = action.keys or []
        if fallback_dispatcher is not None and keys:
            try:
                main_key = keys[-1]
                mods     = keys[:-1]
                if asyncio.iscoroutinefunction(fallback_dispatcher.press_key):
                    result = await fallback_dispatcher.press_key(main_key, mods)
                else:
                    fallback_dispatcher.press_key(main_key, mods)
                    result = ActionResult(success=True, method_used="sendinput_hotkey")
            except Exception as exc:
                result = ActionResult(success=False, error=str(exc))
        else:
            result = ActionResult(success=False, error="No fallback dispatcher for HOTKEY")

    # ---- WAIT ----
    elif action.action_type == ActionType.WAIT:
        await asyncio.sleep(action.timeout_ms / 1000.0)
        result = ActionResult(success=True, method_used="wait")

    if result is None:
        result = ActionResult(success=False, error="No execution path succeeded")

    result.duration_ms = (time.monotonic() - t0) * 1000
    logger.info("execute_action %s → %s via %s (%.1f ms)",
                action.action_type.value, result.success, result.method_used, result.duration_ms)
    return result
