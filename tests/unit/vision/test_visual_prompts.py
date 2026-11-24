"""YOLOE with visual prompts: reference renders of each part type, no training."""

import importlib.util

import pytest

from airc.twin.catalogue import PartCatalogue
from airc.vision import models
from airc.vision.detector import LabelMap, ModelsMissingError, OpenVinoDetector
from airc.vision.references import reference_scenes, render_scene

pytestmark = [pytest.mark.vision, pytest.mark.render]


def test_reference_scenes_are_seeded_and_show_every_class() -> None:
    a = reference_scenes(seed=5, count=3)
    b = reference_scenes(seed=5, count=3)
    assert a == b
    for scene in a:
        assert sorted(c for c, *_ in scene) == [0, 1, 2]


def test_rendered_scene_boxes_match_the_parts() -> None:
    img, boxes, classes = render_scene(reference_scenes(seed=5, count=1)[0], seed=1)
    assert img.shape == (640, 640, 3)
    assert len(boxes) == len(classes) == 3
    for x0, y0, x1, y1 in boxes:
        assert 0 <= x0 < x1 <= 640
        assert 0 <= y0 < y1 <= 640


@pytest.fixture(scope="module")
def detector() -> OpenVinoDetector:
    if importlib.util.find_spec("ultralytics") is None:
        pytest.skip("detectors not installed (uv sync --group vision)")
    try:
        return OpenVinoDetector(
            models.yoloe_dir("visual"), LabelMap.for_slugs(PartCatalogue.load())
        )
    except ModelsMissingError as exc:
        pytest.skip(str(exc))


def test_visual_prompts_classify_unseen_scenes(detector: OpenVinoDetector) -> None:
    correct = total = 0
    for k, scene in enumerate(reference_scenes(seed=900, count=12, min_parts=1)):  # held out
        img, boxes, classes = render_scene(scene, seed=900 + k)
        found = detector.detect(img[:, :, ::-1].copy())  # render_scene returns BGR
        for box, cls in zip(boxes, classes, strict=True):
            total += 1
            best = max(found, key=lambda d: _iou(d.box_xyxy, box), default=None)
            if best is not None and _iou(best.box_xyxy, box) > 0.5 and best.cls == cls:
                correct += 1
    assert correct / total >= 0.9, f"{correct}/{total}"


def _iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
