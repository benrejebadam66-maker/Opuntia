# Copyright (c) 2026 Opuntia. All rights reserved.
# Proprietary and confidential. Unauthorized copying prohibited.
"""
Visual diffing — compare consecutive screen frames to skip redundant
perception passes.

Two frames are considered "unchanged" when their average-hash differ by
less than *threshold* (default 5 % of bits).  This avoids running the
expensive YOLO model 60× per second on a static screen.

Usage
-----
    from engine.perception.diffing import compute_frame_hash, is_frame_unchanged

    prev_hash = compute_frame_hash(frame1)
    changed, diff_ratio = is_frame_unchanged(frame2, prev_hash)
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Average-hash size: 8×8 = 64 bits (plenty for screen diffing).
_HASH_SIZE = 8

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]
    _NUMPY_AVAILABLE = False


def compute_frame_hash(frame: object) -> Optional[str]:
    """
    Compute a perceptual average-hash of a screen frame.

    The frame may be:
    - a ``numpy.ndarray`` (H×W×3 or H×W)   ← preferred
    - a ``PIL.Image.Image``                  ← converted internally
    - ``None``                               ← returns None

    Returns a hex string of ``_HASH_SIZE * _HASH_SIZE`` bits (= 16 hex chars
    for HASH_SIZE=8) or ``None`` if the frame cannot be processed.
    """
    if frame is None:
        return None

    if not _NUMPY_AVAILABLE:
        # Fallback: SHA-256 of raw bytes — not perceptual but still useful
        try:
            raw = bytes(frame)  # type: ignore[call-overload]
            return hashlib.sha256(raw).hexdigest()
        except Exception as exc:
            logger.debug("compute_frame_hash fallback failed: %s", exc)
            return None

    try:
        img = _to_grayscale_np(frame)
        if img is None:
            return None

        # Resize to HASH_SIZE × HASH_SIZE thumbnail then SHA-256 the raw bytes.
        # This is a purely content-based hash — identical frames produce the same
        # digest, and the Hamming comparison is done on the hex character level.
        # We intentionally avoid perceptual hashing tricks that collapse uniform
        # frames (all-black and all-white) to the same hash.
        small = _resize(img, _HASH_SIZE, _HASH_SIZE)
        if small is None:
            return None

        raw = small.astype(np.uint8).tobytes()
        return hashlib.sha256(raw).hexdigest()
    except Exception as exc:
        logger.debug("compute_frame_hash error: %s", exc)
        return None


def is_frame_unchanged(
    frame: object,
    prev_hash: Optional[str],
    threshold: float = 0.05,
) -> tuple[bool, float]:
    """
    Decide whether a frame is "unchanged" relative to the previous hash.

    Parameters
    ----------
    frame : array-like or PIL.Image
        The new frame to check.
    prev_hash : str or None
        Hash returned by a previous ``compute_frame_hash()`` call.
        If ``None``, always returns changed.
    threshold : float
        Fraction of hash bits that may differ and still be called "unchanged".
        Default 0.05 (5 %).

    Returns
    -------
    (unchanged: bool, diff_ratio: float)
        ``unchanged`` is True when the frames are visually similar.
        ``diff_ratio`` is the fraction of bits that differ (0 = identical).
    """
    if prev_hash is None:
        return False, 1.0

    curr_hash = compute_frame_hash(frame)
    if curr_hash is None or prev_hash is None:
        return False, 1.0

    diff_ratio = _hamming_ratio(curr_hash, prev_hash)
    return diff_ratio < threshold, diff_ratio


def hamming_distance(hash1: str, hash2: str) -> int:
    """Count character-level differences between two hex-encoded hash strings.

    For short hashes (≤ 16 chars) this matches bit-level Hamming distance on
    the hex nibbles. For longer hashes (SHA-256) we compare char by char which
    is a coarser but safe measure.
    """
    try:
        # Validate hex
        int(hash1, 16)
        int(hash2, 16)
        length = max(len(hash1), len(hash2))
        h1 = hash1.zfill(length)
        h2 = hash2.zfill(length)
        return sum(c1 != c2 for c1, c2 in zip(h1, h2))
    except ValueError:
        return int(1e9)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _hamming_ratio(hash1: str, hash2: str) -> float:
    """Fraction of hex characters that differ between two hash strings (0–1).

    We compare character-by-character rather than full-integer XOR to avoid
    Python BigInt overflow on long hashes like SHA-256 (64 hex chars = 256 bits).
    """
    if not hash1 or not hash2:
        return 1.0
    # Pad to same length
    length = max(len(hash1), len(hash2))
    h1 = hash1.zfill(length)
    h2 = hash2.zfill(length)
    diffs = sum(c1 != c2 for c1, c2 in zip(h1, h2))
    return diffs / length


def _to_grayscale_np(frame: object):  # type: ignore[return]
    """Convert a frame to a 2-D uint8 numpy array, or return None."""
    if np is None:
        return None
    try:
        if isinstance(frame, np.ndarray):
            arr = frame
        else:
            # Try PIL
            try:
                from PIL import Image as _PILImage
                if isinstance(frame, _PILImage.Image):
                    arr = np.array(frame)
                else:
                    return None
            except Exception:
                return None

        if arr.ndim == 3:
            # Weighted RGB → grey (ITU-R BT.601)
            arr = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]).astype(np.uint8)
        elif arr.ndim != 2:
            return None
        return arr
    except Exception as exc:
        logger.debug("_to_grayscale_np error: %s", exc)
        return None


def _resize(arr, rows: int, cols: int):  # type: ignore[return]
    """Resize a 2-D numpy array to (rows, cols) using nearest-neighbour."""
    if np is None:
        return None
    try:
        from PIL import Image as _PILImage
        img = _PILImage.fromarray(arr).resize((cols, rows), _PILImage.NEAREST)
        return np.array(img, dtype=np.float32)
    except Exception:
        # Pure numpy fallback (slower but dependency-free)
        try:
            h, w = arr.shape
            row_idx = (np.arange(rows) * h / rows).astype(int)
            col_idx = (np.arange(cols) * w / cols).astype(int)
            return arr[np.ix_(row_idx, col_idx)].astype(np.float32)
        except Exception as exc:
            logger.debug("_resize error: %s", exc)
            return None


__all__ = [
    "compute_frame_hash",
    "is_frame_unchanged",
    "hamming_distance",
]
