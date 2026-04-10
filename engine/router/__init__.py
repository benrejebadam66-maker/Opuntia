# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Action router — selects the best execution path for each action.

Priority: native API adapter → MCP bridge → UIA pattern → SendInput fallback.
"""

__all__ = ["route_action"]


def route_action(action, element_map=None):  # noqa: ANN001
    """Lazy proxy — delegates to routing.route_action on first call."""
    from engine.router.routing import route_action as _route
    return _route(action, element_map=element_map)
