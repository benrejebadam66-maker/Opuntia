# Phase 2: Vision + Fusion + Router
# CONFIDENTIAL — [YOUR STARTUP NAME]

## Goal
Add Tier 3 perception (vision model), the fusion layer that merges UIA + vision
detections, and the hybrid action router that picks the fastest reliable method
per action. By the end: the engine sees BOTH structured UIA elements AND
custom-drawn UI that UIA misses, and routes actions through APIs when possible.

## What's Built (Phase 1 — complete)
- engine/perception/accessibility.py — Windows UIA tree walker ✓
- engine/execution/actions.py — UIA-first, SendInput fallback ✓
- engine/execution/verification.py — pre/post state diff ✓
- engine/privacy/scanner.py — PII regex detection + redaction ✓
- engine/observability/tracing.py — JSON traces ✓
- engine/compat/input_control_bridge.py — dispatcher bridge ✓
- Integration into windows_agent.py ✓

## Scope — Build These

### 1. Vision Perception: engine/perception/vision.py
Use ONNX Runtime + YOLOv8-nano model fine-tuned for UI elements.
- Input: screenshot frame (numpy array from screen_capture.py)
- Run YOLOv8 inference via onnxruntime
- Output: list of detected UI elements with bounding boxes, class labels, confidence
- Classes: button, text_field, checkbox, dropdown, link, icon, tab, menu_item
- Convert detections to Element type with source_tier=VISION
- Each element gets a generated ID like "vis_001", "vis_002"

If no ONNX model file exists yet, create a STUB that:
- Takes a screenshot
- Returns an empty list
- Logs a warning: "Vision model not loaded, skipping Tier 3"
This lets the fusion layer work without blocking on model training.

### 2. OCR Fallback: engine/perception/ocr.py
Use Tesseract (pytesseract) for text extraction from screenshots.
- Input: screenshot frame or region crop
- Output: list of detected text blocks with bounding boxes
- Convert to Element type with source_tier=OCR
- Used only when UIA and vision both miss elements

### 3. Visual Diffing: engine/perception/diffing.py
Compare consecutive frames to skip redundant perception passes.
- Input: current frame, previous frame hash
- Compute perceptual hash (average hash or dhash)
- If diff ratio < threshold (default 5%), return "no change"
- Saves 60-80% of vision model inference calls

### 4. Fusion Layer: engine/perception/fusion.py
Merge elements from all active perception tiers into unified ElementMap.
- Input: UIA elements, vision elements, OCR elements
- Deduplicate: if UIA element and vision detection overlap (IoU >= 0.7),
  keep the UIA element (higher confidence, has patterns)
- Sort by confidence descending
- Output: single ElementMap with best-available data per element

Update engine/perception/__init__.py:
```python
async def perceive(app_name=None, tier="all") -> ElementMap:
    uia_elements = await perceive_accessibility(app_name)

    if tier in ("all", "vision") and frame is not None:
        if not is_frame_unchanged(frame):  # diffing
            vision_elements = detect_ui_elements(frame)
        else:
            vision_elements = []
    else:
        vision_elements = []

    return fuse(uia_elements, vision_elements)
```

### 5. Action Router: engine/router/routing.py
Decide HOW to execute each action. Priority:
1. Native API — if action maps to a known API (file ops, web requests)
2. MCP Tool — check existing mcp_bridge.py for matching tool
3. UIA Pattern — use InvokePattern, ValuePattern, etc.
4. SendInput — raw injection via input_control_bridge

```python
def route_action(action: Action, element: Element, available_apis, mcp_tools) -> ExecutionMethod:
    """Returns the best execution method for this action."""
```

### 6. API Adapters: engine/router/api_adapters.py
Native API shortcuts for common tasks:
- FileAdapter: os.path, shutil for file operations
- WebAdapter: requests/httpx for web API calls
- ClipboardAdapter: win32clipboard for copy/paste
Each adapter returns ActionResult directly — no GUI interaction needed.

### 7. Update engine/__init__.py
Export new modules: fuse, route_action, detect_ui_elements

### 8. Tests
- tests/test_vision.py — stub returns empty, integration with real model
- tests/test_ocr.py — Tesseract on test image
- tests/test_diffing.py — same frame → no change, different → changed
- tests/test_fusion.py — merge UIA + vision, dedup, confidence sort
- tests/test_router.py — routing priority logic
- tests/test_api_adapters.py — file, web, clipboard adapters

## Acceptance Criteria
- [ ] perceive(tier="all") returns fused elements from UIA + vision
- [ ] Vision stub works without ONNX model (returns empty, no crash)
- [ ] Diffing skips vision when frame unchanged
- [ ] Fusion deduplicates overlapping UIA + vision elements
- [ ] Router picks UIA over SendInput, API over UIA when available
- [ ] File operations route through API adapter (no GUI)
- [ ] All Phase 1 tests still pass
- [ ] version0.2.py still works unchanged

## NOT in Phase 2
- DAG orchestrator, intent interpreter
- Human-in-the-loop gates
- Docker sandbox
- Progressive permissions
- CLI binary
- Linux/macOS support
- MCP client rewrite (use existing mcp_bridge.py)
