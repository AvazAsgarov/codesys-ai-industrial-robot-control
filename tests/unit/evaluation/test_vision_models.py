"""The real detectors on a few rendered frames (need the exported models; marked vision)."""

import pytest

from airc.evaluation.dataset import render_dataset
from airc.evaluation.vision_eval import evaluate, make_detector
from airc.twin.config import TwinConfig
from airc.vision.detector import Detector, ModelsMissingError

pytestmark = [pytest.mark.vision, pytest.mark.render]


def _detector(kind: str, cfg: TwinConfig, quarter_turns: int = 0) -> Detector:
    try:
        return make_detector(kind, "classes", cfg, quarter_turns=quarter_turns)
    except (ModelsMissingError, ImportError) as exc:
        pytest.skip(str(exc))


def test_yoloe_visual_prompts_find_the_parts_near_pe1() -> None:
    cfg = TwinConfig.load(parts="catalogue")
    detector = _detector("yoloe-visual", cfg)
    assert detector.name.startswith("yoloe-26s-seg-visual")
    result = evaluate(detector, render_dataset(301, 10, cfg))
    assert result["mAP50"] > 0.8
    assert result["pose_mm"]["mean"] < 10.0


def test_yoloe_text_prompts_find_the_parts_near_pe1() -> None:
    cfg = TwinConfig.load(parts="catalogue")
    result = evaluate(_detector("yoloe", cfg, quarter_turns=1), render_dataset(300, 10, cfg))
    assert result["mAP50"] > 0.3


def test_visual_prompts_need_the_classes_they_were_made_for() -> None:
    cfg = TwinConfig.load(parts="catalogue", classes=["ink_cartridge", "vitamin_jar", "coffee_can"])
    with pytest.raises(ValueError, match="ink_cartridge"):
        _detector("yoloe-visual", cfg)
