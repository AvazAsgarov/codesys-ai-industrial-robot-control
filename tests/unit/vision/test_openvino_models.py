"""The exported detectors on rendered frames (local: needs `airc vision export`)."""

import importlib.util

import numpy as np
import pytest

from airc.twin.catalogue import PartCatalogue
from airc.twin.config import TwinConfig
from airc.twin.twin import PartSpec, Twin
from airc.vision import models
from airc.vision.detector import LabelMap, ModelsMissingError, OpenVinoDetector
from airc.vision.render import FrameRenderer

pytestmark = [pytest.mark.vision, pytest.mark.render]


@pytest.fixture(scope="module")
def detector() -> OpenVinoDetector:
    if importlib.util.find_spec("ultralytics") is None:
        pytest.skip("detectors not installed (uv sync --group vision)")
    try:
        return OpenVinoDetector(  # a pipeline check, not an accuracy check (Task 7 measures that)
            models.yoloe_dir("classes"), LabelMap.for_prompts(PartCatalogue.load()), conf=0.01
        )
    except ModelsMissingError as exc:
        pytest.skip(str(exc))


def test_exported_yoloe_keeps_the_prompts(detector: OpenVinoDetector) -> None:
    prompts = [p.prompt for p in PartCatalogue.load().classes]
    names = detector._model.names
    assert [names[i] for i in sorted(names)] == prompts


def test_detection_mask_lies_on_the_part(detector: OpenVinoDetector) -> None:
    """Pipeline check (BGR input, ROI, image-sized masks): the detector's mask of a part it
    finds lies on that part. Which classes zero-shot finds is the Task 7 benchmark's job."""
    roi = (slice(40, 680), slice(320, 960))  # 640 x 640 around PE1 (the image centre)
    ious: list[float] = []
    for cls in range(3):
        twin = Twin(cfg=TwinConfig.load(parts="catalogue"))
        renderer = FrameRenderer(twin.model, "cam_inspect", twin.cfg)
        pid = twin.spawn(PartSpec(cls=cls, y_mm=0.0, theta_deg=10.0, x_mm=twin.geo.pe1_x))
        twin.step(twin.joint_positions_rad(), 0.0, 0.0, False)
        frame = renderer.render(twin.data)
        renderer.close()
        found = detector.detect(np.ascontiguousarray(frame.rgb[roi]))
        truth = frame.body_mask(twin.part_body_id(pid))[roi]
        for det in found:
            assert det.mask.shape == truth.shape
            ious.append(float((det.mask & truth).sum() / (det.mask | truth).sum()))
    assert ious, "no class detected at all"
    assert max(ious) > 0.5
