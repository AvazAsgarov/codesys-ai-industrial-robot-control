"""Metrics for the zero-shot detector benchmark against simulator ground truth.

Detection quality is precision, recall and AP@0.5 per class (COCO-style all-point interpolation);
pose quality is position error in mm and angle error in degrees (respecting part symmetry);
latency and errors are summarised by mean, median, p95 and max.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Box:
    """Axis-aligned box in pixels, ``(x0, y0)`` top-left and ``(x1, y1)`` bottom-right."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def area(self) -> float:
        """Box area in square pixels (0 for a degenerate box)."""
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)


@dataclass(frozen=True)
class Detection:
    """One detector output in one frame."""

    frame: int
    cls: int
    confidence: float
    box: Box


@dataclass(frozen=True)
class Truth:
    """One ground-truth object in one frame."""

    frame: int
    cls: int
    box: Box


@dataclass(frozen=True)
class ClassStats:
    """Detection quality for one class.

    ``precision`` and ``recall`` are counted at the confidence threshold; ``ap50`` uses every
    detection. ``n_det`` counts the detections at or above the confidence threshold.
    """

    precision: float
    recall: float
    ap50: float
    n_truth: int
    n_det: int


def iou(a: Box, b: Box) -> float:
    """Intersection over union of two boxes (0 when they do not overlap)."""
    inter = Box(max(a.x0, b.x0), max(a.y0, b.y0), min(a.x1, b.x1), min(a.y1, b.y1)).area
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


def _match(
    detections: Sequence[Detection], truths: Sequence[Truth], cls: int, iou_threshold: float
) -> list[bool]:
    """Greedy matching of one class's detections, highest confidence first.

    Returns one flag per detection of ``cls`` in descending confidence order: True for a true
    positive. Each truth is matched at most once, to the detection that reaches it first.
    """
    dets = sorted((d for d in detections if d.cls == cls), key=lambda d: -d.confidence)
    by_frame: dict[int, list[int]] = {}
    for i, t in enumerate(truths):
        if t.cls == cls:
            by_frame.setdefault(t.frame, []).append(i)
    used: set[int] = set()
    hits: list[bool] = []
    for det in dets:
        best_iou, best_id = iou_threshold, -1
        for i in by_frame.get(det.frame, []):
            overlap = iou(det.box, truths[i].box)
            if i not in used and overlap >= best_iou:
                best_iou, best_id = overlap, i
        if best_id >= 0:
            used.add(best_id)
        hits.append(best_id >= 0)
    return hits


def average_precision(
    detections: Sequence[Detection],
    truths: Sequence[Truth],
    cls: int,
    iou_threshold: float = 0.5,
) -> float:
    """AP of one class with all-point interpolation.

    Args:
        detections: Detector outputs (any classes, any frames).
        truths: Ground truth (any classes, any frames).
        cls: Class to evaluate.
        iou_threshold: Minimum IoU for a detection to match a truth.

    Returns:
        The area under the interpolated precision/recall curve; NaN if the class has no
        truths, 0.0 if it has truths but no detections.
    """
    n_truth = sum(1 for t in truths if t.cls == cls)
    if n_truth == 0:
        return math.nan
    hits = _match(detections, truths, cls, iou_threshold)
    if not hits:
        return 0.0
    tp = np.cumsum(np.array(hits, dtype=np.float64))
    recall = tp / n_truth
    precision = tp / np.arange(1, len(hits) + 1, dtype=np.float64)
    precision = np.maximum.accumulate(precision[::-1])[::-1]
    steps = np.diff(np.concatenate(([0.0], recall)))
    return float(np.sum(steps * precision))


def per_class_stats(
    detections: Sequence[Detection],
    truths: Sequence[Truth],
    classes: Sequence[int],
    iou_threshold: float = 0.5,
    conf_threshold: float = 0.25,
) -> dict[int, ClassStats]:
    """Precision and recall at ``conf_threshold`` plus AP@``iou_threshold`` for each class.

    Precision is NaN for a class with no detections above the threshold; recall is NaN for a
    class with no truths.
    """
    confident = [d for d in detections if d.confidence >= conf_threshold]
    out: dict[int, ClassStats] = {}
    for cls in classes:
        n_truth = sum(1 for t in truths if t.cls == cls)
        hits = _match(confident, truths, cls, iou_threshold)
        tp = sum(hits)
        out[cls] = ClassStats(
            precision=tp / len(hits) if hits else math.nan,
            recall=tp / n_truth if n_truth else math.nan,
            ap50=average_precision(detections, truths, cls, iou_threshold),
            n_truth=n_truth,
            n_det=len(hits),
        )
    return out


def mean_ap(stats: Mapping[int, ClassStats]) -> float:
    """Mean of the per-class AP, ignoring classes without truths (NaN if none are left)."""
    aps = [s.ap50 for s in stats.values() if not math.isnan(s.ap50)]
    return sum(aps) / len(aps) if aps else math.nan


def angle_error_deg(est: float, true: float, symmetry: int) -> float:
    """Absolute angle error in degrees for a part with ``symmetry``-fold rotational symmetry.

    Args:
        est: Estimated angle in degrees.
        true: True angle in degrees.
        symmetry: 1 for no symmetry, n for n-fold symmetry (2: 180 degrees), 0 for round parts.

    Returns:
        The error in ``[0, 180 / symmetry]``; always 0.0 for round parts.
    """
    if symmetry == 0:
        return 0.0
    if symmetry < 0:
        msg = f"symmetry must be >= 0, got {symmetry}"
        raise ValueError(msg)
    period = 360.0 / symmetry
    diff = abs(est - true) % period
    return min(diff, period - diff)


def position_error_mm(est_xy: tuple[float, float], true_xy: tuple[float, float]) -> float:
    """Euclidean distance between estimated and true position in mm."""
    return math.hypot(est_xy[0] - true_xy[0], est_xy[1] - true_xy[1])


def percentile_summary(values: Sequence[float]) -> dict[str, float]:
    """Mean, median, p95, max and count of ``values`` (all NaN except ``n`` when empty)."""
    if not values:
        return {"mean": math.nan, "p50": math.nan, "p95": math.nan, "max": math.nan, "n": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.mean(arr)),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "max": float(np.max(arr)),
        "n": float(arr.size),
    }
