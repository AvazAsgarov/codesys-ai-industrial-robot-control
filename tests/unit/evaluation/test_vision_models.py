"""The real YOLOE-26 on a few rendered frames (needs the exported model; marked vision)."""

import pytest

from airc.evaluation.dataset import render_dataset
from airc.evaluation.vision_eval import evaluate, make_detector
from airc.twin.config import TwinConfig
from airc.vision.detector import ModelsMissingError

pytestmark = [pytest.mark.vision, pytest.mark.render]


def test_yoloe_finds_the_parts_near_pe1() -> None:
    cfg = TwinConfig.load(parts="catalogue")
    try:
        detector = make_detector("yoloe", "classes", cfg, quarter_turns=1)
    except (ModelsMissingError, ImportError) as exc:
        pytest.skip(str(exc))
    result = evaluate(detector, render_dataset(300, 10, cfg))
    assert result["mAP50"] > 0.3
