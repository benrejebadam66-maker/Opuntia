# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Vision-based UI element detection — Tier 3 perception.

Uses YOLOv8-nano ONNX model fine-tuned on UI elements. When the model file
does not exist, the function returns an empty list and logs a warning —
the rest of the pipeline continues with UIA elements only.

Model classes (index → label):
    0: button      1: text_field   2: checkbox    3: dropdown
    4: link        5: icon         6: tab         7: menu_item

Usage
-----
    from engine.perception.vision import detect_ui_elements

    elements = detect_ui_elements(frame)          # frame: np.ndarray H×W×3
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Default model path (relative to the project root or absolute via env var).
_DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "models",
    "ui-detector.onnx",
)

# Class index → control type string used in Element.control_type
_CLASS_NAMES = [
    "Button",
    "Edit",
    "CheckBox",
    "ComboBox",
    "Hyperlink",
    "Image",
    "TabItem",
    "MenuItem",
]

# YOLOv8 inference settings
_INPUT_SIZE   = 640        # standard YOLOv8 input edge
_CONF_THRESH  = 0.35       # minimum confidence to emit a detection
_IOU_THRESH   = 0.45       # NMS IoU threshold

# Lazy-loaded ONNX session — initialised once on first call
_onnx_session = None
_model_path_loaded: Optional[str] = None

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]
    _NUMPY_AVAILABLE = False

try:
    import onnxruntime as ort
    _ORT_AVAILABLE = True
except ImportError:
    ort = None  # type: ignore[assignment]
    _ORT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_ui_elements(
    frame: object,
    model_path: Optional[str] = None,
) -> list:
    """
    Detect UI elements in a screenshot frame via YOLOv8-nano ONNX inference.

    Parameters
    ----------
    frame : numpy.ndarray (H × W × 3, uint8) or None
        Screenshot to analyse.  If ``None`` or if the model is unavailable,
        returns an empty list without raising.
    model_path : str, optional
        Path to the ONNX model file.  Defaults to ``models/ui-detector.onnx``
        next to the project root.

    Returns
    -------
    list[Element]
        Detected elements with ``source_tier=VISION``.  Empty list when the
        model is not loaded or the frame is None.
    """
    if frame is None:
        return []

    resolved_path = model_path or _DEFAULT_MODEL_PATH
    session = _get_session(resolved_path)

    if session is None:
        # Stub mode — model not available
        return []

    if not _NUMPY_AVAILABLE:
        logger.warning("numpy not available — vision detection skipped")
        return []

    try:
        return _run_inference(session, frame)  # type: ignore[arg-type]
    except Exception as exc:
        logger.error("Vision inference failed: %s", exc)
        return []


def is_model_available(model_path: Optional[str] = None) -> bool:
    """Return True if the ONNX model file exists and onnxruntime is installed."""
    path = model_path or _DEFAULT_MODEL_PATH
    return _ORT_AVAILABLE and os.path.isfile(path)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_session(model_path: str):
    """Lazy-load the ONNX session (cached after first load)."""
    global _onnx_session, _model_path_loaded

    if _onnx_session is not None and _model_path_loaded == model_path:
        return _onnx_session

    if not _ORT_AVAILABLE:
        logger.warning("onnxruntime not installed — vision detection disabled")
        return None

    if not os.path.isfile(model_path):
        logger.warning(
            "Vision model not loaded, skipping Tier 3 (expected at %s)", model_path
        )
        return None

    try:
        opts = ort.SessionOptions()
        opts.log_severity_level = 3  # suppress verbose ORT logs
        session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        _onnx_session = session
        _model_path_loaded = model_path
        logger.info("Vision model loaded from %s", model_path)
        return session
    except Exception as exc:
        logger.error("Failed to load vision model from %s: %s", model_path, exc)
        return None


def _run_inference(session, frame: "np.ndarray") -> list:
    """Run YOLO inference and convert detections to Element objects."""
    from engine.types import (
        Action, BoundingBox, Element, ElementState, PerceptionTier,
    )

    orig_h, orig_w = frame.shape[:2]
    inp = _preprocess(frame)

    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: inp})

    # YOLOv8 output shape: (1, num_classes+4, num_boxes) in transposed form
    # or (1, num_boxes, 5+num_classes) — handle both
    raw = outputs[0]
    detections = _parse_output(raw, orig_w, orig_h)

    elements = []
    for i, det in enumerate(detections):
        x1, y1, x2, y2, conf, cls_idx = det
        cls_idx = int(cls_idx)
        ctrl_type = _CLASS_NAMES[cls_idx] if cls_idx < len(_CLASS_NAMES) else "Custom"
        bbox = BoundingBox(
            x=int(x1), y=int(y1),
            width=max(1, int(x2 - x1)),
            height=max(1, int(y2 - y1)),
        )
        el_id = f"vis_{i:03d}"
        actions: list[str] = ["click"]
        if ctrl_type in ("Edit",):
            actions.append("set_value")
        elements.append(Element(
            id=el_id,
            label=f"{ctrl_type} (vision)",
            control_type=ctrl_type,
            bbox=bbox,
            actions=actions,
            state=ElementState(),
            confidence=float(conf),
            source_tier=PerceptionTier.VISION,
        ))
    return elements


def _preprocess(frame: "np.ndarray") -> "np.ndarray":
    """Resize frame to _INPUT_SIZE × _INPUT_SIZE and normalise to [0,1]."""
    from PIL import Image as _PILImage
    img = _PILImage.fromarray(frame[..., :3]).resize(
        (_INPUT_SIZE, _INPUT_SIZE), _PILImage.BILINEAR
    )
    arr = np.array(img, dtype=np.float32) / 255.0
    # CHW + batch dimension
    return arr.transpose(2, 0, 1)[np.newaxis, ...]


def _parse_output(raw: "np.ndarray", orig_w: int, orig_h: int) -> list[tuple]:
    """
    Parse YOLOv8 output into (x1, y1, x2, y2, conf, cls) tuples in original
    pixel coordinates, with NMS applied.

    YOLOv8 export format: (1, 4 + num_classes, num_boxes) — rows are
    cx, cy, w, h, *class_scores.  Transpose to (num_boxes, …) first.
    """
    if raw.ndim == 3:
        # shape (1, features, boxes) → (boxes, features)
        raw = raw[0].T
    elif raw.ndim == 2:
        pass  # already (boxes, features)
    else:
        return []

    num_classes = len(_CLASS_NAMES)
    if raw.shape[1] < 5:
        return []

    box_coords = raw[:, :4]        # cx, cy, w, h (normalised 0–1)
    class_scores = raw[:, 4:4 + num_classes]
    conf = class_scores.max(axis=1)
    cls = class_scores.argmax(axis=1)

    # Filter by confidence
    mask = conf > _CONF_THRESH
    box_coords = box_coords[mask]
    conf = conf[mask]
    cls = cls[mask]

    # Convert cx/cy/w/h → x1/y1/x2/y2 in original pixel space
    scale_x, scale_y = orig_w / _INPUT_SIZE, orig_h / _INPUT_SIZE
    x1 = (box_coords[:, 0] - box_coords[:, 2] / 2) * _INPUT_SIZE * scale_x
    y1 = (box_coords[:, 1] - box_coords[:, 3] / 2) * _INPUT_SIZE * scale_y
    x2 = (box_coords[:, 0] + box_coords[:, 2] / 2) * _INPUT_SIZE * scale_x
    y2 = (box_coords[:, 1] + box_coords[:, 3] / 2) * _INPUT_SIZE * scale_y

    boxes = np.stack([x1, y1, x2, y2], axis=1)
    kept = _nms(boxes, conf, _IOU_THRESH)
    return [(boxes[i, 0], boxes[i, 1], boxes[i, 2], boxes[i, 3], conf[i], cls[i])
            for i in kept]


def _nms(boxes: "np.ndarray", scores: "np.ndarray", iou_thresh: float) -> list[int]:
    """Simple greedy NMS. Returns kept indices in descending confidence order."""
    order = scores.argsort()[::-1]
    kept = []
    while len(order):
        i = order[0]
        kept.append(int(i))
        if len(order) == 1:
            break
        rest = order[1:]
        iou = _iou_batch(boxes[i], boxes[rest])
        order = rest[iou < iou_thresh]
    return kept


def _iou_batch(box: "np.ndarray", others: "np.ndarray") -> "np.ndarray":
    """IoU of one box against N others."""
    ix1 = np.maximum(box[0], others[:, 0])
    iy1 = np.maximum(box[1], others[:, 1])
    ix2 = np.minimum(box[2], others[:, 2])
    iy2 = np.minimum(box[3], others[:, 3])
    inter = np.maximum(0, ix2 - ix1) * np.maximum(0, iy2 - iy1)
    area1 = (box[2] - box[0]) * (box[3] - box[1])
    area2 = (others[:, 2] - others[:, 0]) * (others[:, 3] - others[:, 1])
    union = area1 + area2 - inter
    return inter / np.maximum(union, 1e-6)


__all__ = ["detect_ui_elements", "is_model_available"]
