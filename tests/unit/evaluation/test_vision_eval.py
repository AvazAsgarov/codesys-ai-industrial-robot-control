"""Vision benchmark: detections against rendered ground truth."""

import json
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from airc.cli import app
from airc.evaluation.dataset import render_dataset
from airc.evaluation.vision_eval import OracleDetector, evaluate, match_frame
from airc.twin.config import TwinConfig
from airc.vision.detector import Detection

SLUGS = ["probiotic_box", "vitamin_jar", "coffee_can"]


def _det(cls: int | None, conf: float, box: tuple[float, float, float, float]) -> Detection:
    return Detection("x", cls, conf, box, np.zeros((4, 4), dtype=bool))


def test_match_frame_pairs_best_iou_of_the_same_class_once() -> None:
    truths = [(0, (0.0, 0.0, 10.0, 10.0)), (1, (20.0, 20.0, 30.0, 30.0))]
    dets = [
        _det(0, 0.9, (0.0, 0.0, 10.0, 10.0)),
        _det(0, 0.8, (1.0, 1.0, 10.0, 10.0)),  # duplicate: the truth is taken
        _det(0, 0.7, (20.0, 20.0, 30.0, 30.0)),  # wrong class
        _det(None, 0.9, (20.0, 20.0, 30.0, 30.0)),  # not a part
    ]
    assert match_frame(dets, truths, conf=0.25) == {0: 0}
    assert match_frame(dets, truths, conf=0.95) == {}


@pytest.mark.render
def test_oracle_gives_perfect_map_and_small_pose_error(tmp_path: Path) -> None:
    cfg = TwinConfig.load(parts="catalogue")
    oracle = OracleDetector()
    result = evaluate(oracle, render_dataset(31, 8, cfg, SLUGS), frame_hook=oracle.see)
    assert result["frames"] == 8
    assert result["mAP50"] == pytest.approx(1.0)
    for slug in SLUGS:
        assert result["per_class"][slug]["AP50"] == pytest.approx(1.0)
        assert result["per_class"][slug]["R"] == pytest.approx(1.0)
    assert result["pose_mm"]["mean"] < 5.0
    assert result["pose_mm"]["n"] > 8
    assert result["theta_deg"]["mean"] < 2.0  # probiotic_box: nearly square, 57 mm tall
    assert result["theta_deg"]["p95"] < 4.0
    assert result["latency_ms"]["p50"] >= 0.0


@pytest.mark.render
def test_cli_eval_vision_with_oracle(tmp_path: Path) -> None:
    out = tmp_path / "vision.json"
    res = CliRunner().invoke(
        app,
        [
            "eval", "vision", "--detector", "oracle", "--seed", "3", "--frames", "2",
            "--tilt", "40", "--classes", ",".join(SLUGS), "--out", str(out),
        ],
    )  # fmt: skip
    assert res.exit_code == 0, res.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["detector"] == "oracle"
    assert data["tilt"] == 40.0
    assert data["classes"] == SLUGS
    assert data["seed"] == 3
    assert data["mAP50"] == pytest.approx(1.0)


def test_cli_eval_vision_rejects_unknown_detector() -> None:
    res = CliRunner().invoke(app, ["eval", "vision", "--detector", "nope", "--frames", "1"])
    assert res.exit_code == 2
    assert "--detector" in res.output


@pytest.mark.render
def test_oracle_theta_is_the_part_yaw_for_a_box_long_along_its_y() -> None:
    slugs = ["candy_box", "vitamin_jar", "coffee_can"]  # candy box: 67 x 115 mm footprint
    cfg = TwinConfig.load(parts="catalogue", classes=slugs)
    oracle = OracleDetector()
    result = evaluate(oracle, render_dataset(41, 12, cfg), frame_hook=oracle.see)
    assert result["theta_deg"]["n"] >= 3
    assert result["theta_deg"]["mean"] < 3.0
