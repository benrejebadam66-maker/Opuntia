# Phase 2 Implementation Lessons

## Visual Diffing (Step 1)

**Lesson**: Average-hash and dhash both collapse uniform frames (all-black == all-white), because they compare against the mean or adjacent pixels — producing all-zero bit vectors for any uniform image.

**Fix**: Use SHA-256 of a resized 8×8 grayscale thumbnail. This is content-based (not gradient-based), so identical pixels produce identical hashes and different pixels produce different hashes. Works correctly for all-black, all-white, and gradient frames.

**Lesson**: For SHA-256 hashes (64 hex chars = 256 bits), full-integer XOR on Python BigInts can be unreliable and produces unexpected Hamming distances. 

**Fix**: Character-level Hamming comparison (count mismatched hex chars). Coarser than bit-level but safe and sufficient for 5% change detection on screen captures.

---

## Vision Stub (Step 2)

**Lesson**: `_onnx_session` is module-level state. If you pass a different `model_path` on a subsequent call, the cached session must be invalidated.

**Fix**: Track `_model_path_loaded` alongside `_onnx_session` and reload when the path changes.

**Lesson**: YOLOv8 ONNX output can come in two orientations: `(1, features, boxes)` or `(1, boxes, features)`. Handle both by checking `ndim` and transposing when needed.

---

## Fusion Layer (Step 4)

**Lesson**: Confidence capping for lower-tier elements prevents vision/OCR detections from outranking UIA results near a confidence boundary. Cap vision at 0.95, OCR at 0.85.

**Lesson**: The fusion layer should be a pure function (no side effects, no I/O). This makes it easy to test exhaustively with synthetic data.

**Lesson**: IoU threshold of 0.7 works well for UI elements because they tend to be rectangular and axis-aligned. Lower thresholds (0.3–0.5) cause too many false duplicates for overlapping labels/icons.

---

## Tiered Pipeline (Step 5)

**Lesson**: Visual diffing should gate only Tiers 2–3, never Tier 1. UIA is cheap (< 50 ms) and must always reflect current state. YOLO and Tesseract are expensive (200–800 ms) and are safe to cache for unchanged screens.

**Lesson**: Module-level `_prev_hash` / `_cached_map` variables make the pipeline stateful. This is intentional for performance but means tests must reset these or patch them to avoid cross-test contamination.

---

## API Adapters (Step 6)

**Lesson**: `win32clipboard` is widely available on Windows Python installations but requires try/except for import since it's not in stdlib. Always fall back to `pyperclip`.

**Lesson**: `httpx` is preferred over `requests` for the web adapter because it has better async support. However, for synchronous calls (as used here) both work identically.

**Lesson**: Path detection heuristic (`_looks_like_path`) must handle both Windows (`C:\path`) and Unix (`/path`) conventions, because the engine may run tests on either platform.

---

## Hybrid Router (Step 7)

**Lesson**: `MCPBridge.__init__()` requires a `config_path` argument. The router's `_try_mcp` must catch `TypeError` (and all exceptions) to degrade gracefully.

**Lesson**: Calling an async function (`execute_action`) from a synchronous router requires a thread + `asyncio.run()`. Using `loop.run_until_complete()` fails when already inside a running loop (common in test environments). The correct pattern is a `ThreadPoolExecutor` with `asyncio.run()` inside the worker thread.

**Fix**: `_try_uia` in `routing.py` now always creates a fresh thread with `concurrent.futures.ThreadPoolExecutor` to avoid event-loop re-entrancy.

---

## Integration with Execute (Step 8)

**Lesson**: Adding `use_router=False` to the recursive call from `_try_uia → execute_action` is critical to prevent infinite recursion (router → UIA → router → ...).

**Lesson**: Making `element_map` Optional in `execute_action` was necessary for the router path, where the caller may not have a live ElementMap. The existing callers that pass an ElementMap are unaffected.

---

## Testing Patterns

- Use `__new__()` bypass for monolithic agent classes that can't be easily instantiated in tests. Set all required attributes manually in the test stub.
- Use `sys.settrace` to intercept swallowed exceptions inside `process_command`-style dispatch methods — faster than one-at-a-time attribute discovery.
- Use `patch.object(module, 'attribute', mock)` for module-level variables like `pytesseract` that are set at import time.
- Pre-existing test failures should be verified with `git stash` before concluding they are not caused by new changes.
