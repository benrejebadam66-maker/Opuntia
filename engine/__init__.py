# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Opuntia Engine — next-gen perception and execution layer.

Public API
----------
    from engine import perceive, execute_action, init_tracing, trace_action
    from engine.types import Action, ActionType, ElementMap
    from engine.privacy import scan_text_for_pii, scan_elements_for_pii, redact_text
    from engine.compat import InputControlBridge
"""

from engine.perception import perceive
from engine.execution.actions import execute_action
from engine.execution.verification import verify_action
from engine.privacy.scanner import scan_text_for_pii, scan_elements_for_pii, redact_text
from engine.observability.tracing import init_tracing, trace_action, get_traces
from engine.compat.input_control_bridge import InputControlBridge
from engine.router.routing import route_action
from engine.types import (
    Action, ActionResult, ActionType,
    BoundingBox, Element, ElementMap, ElementState,
    PerceptionTier, PIIMatch, VerificationResult,
)

__all__ = [
    # Perception
    "perceive",
    # Execution
    "execute_action", "verify_action",
    # Router
    "route_action",
    # Privacy
    "scan_text_for_pii", "scan_elements_for_pii", "redact_text",
    # Observability
    "init_tracing", "trace_action", "get_traces",
    # Compat
    "InputControlBridge",
    # Types
    "Action", "ActionResult", "ActionType",
    "BoundingBox", "Element", "ElementMap", "ElementState",
    "PerceptionTier", "PIIMatch", "VerificationResult",
]
