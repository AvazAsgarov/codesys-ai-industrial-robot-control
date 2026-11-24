"""Detector benchmark metrics: IoU, AP, per-class stats, pose error and summaries."""

import math

import pytest

from airc.evaluation.metrics import (
    Box,
    Detection,
    Truth,
    angle_error_deg,
    average_precision,
    iou,
    mean_ap,
    per_class_stats,
    percentile_summary,
    position_error_mm,
)

BOX = Box(0.0, 0.0, 10.0, 10.0)
FAR = Box(100.0, 100.0, 110.0, 110.0)


def test_iou_identical_and_disjoint() -> None:
    assert iou(BOX, BOX) == 1.0
    assert iou(BOX, FAR) == 0.0
    assert iou(BOX, Box(5.0, 0.0, 15.0, 10.0)) == pytest.approx(1 / 3)


def test_ap_perfect_detections_is_one() -> None:
    truths = [Truth(f, 0, BOX) for f in range(3)]
    dets = [Detection(f, 0, 0.9, BOX) for f in range(3)]
    assert average_precision(dets, truths, cls=0) == pytest.approx(1.0)


def test_ap_hand_computed_case() -> None:
    truths = [Truth(f, 0, BOX) for f in range(3)]
    dets = [
        Detection(0, 0, 0.9, BOX),  # TP
        Detection(1, 0, 0.8, FAR),  # FP
        Detection(1, 0, 0.7, BOX),  # TP
        Detection(2, 0, 0.6, FAR),  # FP
    ]
    # precision 1, 1/2, 2/3, 2/4 at recall 1/3, 1/3, 2/3, 2/3
    assert average_precision(dets, truths, cls=0) == pytest.approx(5 / 9)


def test_ap_duplicate_detection_counts_once() -> None:
    truths = [Truth(0, 0, BOX)]
    dets = [Detection(0, 0, 0.9, BOX), Detection(0, 0, 0.8, BOX)]
    assert average_precision(dets, truths, cls=0) == pytest.approx(1.0)
    stats = per_class_stats(dets, truths, classes=[0])[0]
    assert stats.recall == pytest.approx(1.0)
    assert stats.precision == pytest.approx(0.5)


def test_ap_no_truths_is_nan_and_no_detections_is_zero() -> None:
    assert math.isnan(average_precision([Detection(0, 0, 0.9, BOX)], [], cls=0))
    assert average_precision([], [Truth(0, 0, BOX)], cls=0) == 0.0


def test_detection_of_other_class_does_not_match() -> None:
    truths = [Truth(0, 0, BOX)]
    dets = [Detection(0, 1, 0.9, BOX)]
    assert average_precision(dets, truths, cls=0) == 0.0
    assert math.isnan(average_precision(dets, truths, cls=1))


def test_per_class_stats_and_mean_ap_ignore_absent_classes() -> None:
    truths = [Truth(0, 0, BOX), Truth(1, 0, BOX), Truth(0, 1, FAR)]
    dets = [
        Detection(0, 0, 0.9, BOX),
        Detection(1, 0, 0.1, BOX),  # below the confidence threshold
        Detection(0, 1, 0.8, BOX),  # wrong place: FP for class 1
    ]
    stats = per_class_stats(dets, truths, classes=[0, 1, 2])
    assert stats[0].n_truth == 2
    assert stats[0].n_det == 1
    assert stats[0].precision == pytest.approx(1.0)
    assert stats[0].recall == pytest.approx(0.5)
    assert stats[0].ap50 == pytest.approx(1.0)
    assert stats[1].ap50 == 0.0
    assert stats[1].precision == 0.0
    assert math.isnan(stats[2].ap50)
    assert stats[2].n_truth == 0
    assert mean_ap(stats) == pytest.approx(0.5)


def test_theta_error_respects_symmetry() -> None:
    assert angle_error_deg(179.0, -1.0, 2) == pytest.approx(0.0)
    assert angle_error_deg(10.0, 350.0, 1) == pytest.approx(20.0)
    assert angle_error_deg(90.0, 0.0, 2) == pytest.approx(90.0)
    assert angle_error_deg(37.0, -123.0, 0) == 0.0
    assert angle_error_deg(0.0, 180.0, 1) == pytest.approx(180.0)


def test_position_error_and_summary() -> None:
    assert position_error_mm((0.0, 0.0), (3.0, 4.0)) == pytest.approx(5.0)
    summary = percentile_summary([float(v) for v in range(1, 101)])
    assert summary["n"] == 100.0
    assert summary["mean"] == pytest.approx(50.5)
    assert summary["p50"] == pytest.approx(50.5)
    assert summary["p95"] == pytest.approx(95.05)
    assert summary["max"] == 100.0
    empty = percentile_summary([])
    assert empty["n"] == 0.0
    assert all(math.isnan(empty[k]) for k in ("mean", "p50", "p95", "max"))
