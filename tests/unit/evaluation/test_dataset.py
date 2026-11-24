"""Labelled benchmark frames rendered from the twin (needs an OpenGL context; marked render)."""

import numpy as np
import pytest

from airc.evaluation.dataset import LabelledFrame, render_dataset
from airc.twin.config import TwinConfig
from airc.vision.service import ROI_PX

pytestmark = pytest.mark.render

SLUGS = ["probiotic_box", "vitamin_jar", "coffee_can"]


@pytest.fixture(scope="module")
def cfg() -> TwinConfig:
    return TwinConfig.load(parts="catalogue")


def _frames(cfg: TwinConfig, seed: int, n: int) -> list[LabelledFrame]:
    try:
        return list(render_dataset(seed, n, cfg, SLUGS))
    except Exception as exc:  # no OpenGL context on this machine (e.g. a headless CI runner)
        if "OpenGL" in repr(exc) or "GL" in type(exc).__name__:
            pytest.skip(f"no OpenGL context: {exc}")
        raise


def test_dataset_same_seed_same_frames(cfg: TwinConfig) -> None:
    a = _frames(cfg, 11, 3)
    b = _frames(cfg, 11, 3)
    c = _frames(cfg, 12, 3)
    assert len(a) == 3
    for fa, fb in zip(a, b, strict=True):
        assert np.array_equal(fa.rgb, fb.rgb)
        assert [(p.cls, p.x_mm, p.y_mm, p.theta_deg) for p in fa.parts] == [
            (p.cls, p.x_mm, p.y_mm, p.theta_deg) for p in fb.parts
        ]
    assert any(not np.array_equal(fa.rgb, fc.rgb) for fa, fc in zip(a, c, strict=True))


def test_truth_boxes_match_masks_and_parts_lie_near_pe1(cfg: TwinConfig) -> None:
    frames = _frames(cfg, 21, 6)
    for frame in frames:
        assert frame.rgb.shape == (ROI_PX, ROI_PX, 3)
        assert 1 <= len(frame.parts) <= 3
        assert frame.scene.slugs == tuple(SLUGS)
        for part in frame.parts:
            assert part.cls in (0, 1, 2)
            assert part.mask.shape == (ROI_PX, ROI_PX)
            vs, us = np.nonzero(part.mask)
            assert part.box == (us.min(), vs.min(), us.max() + 1, vs.max() + 1)
            assert np.array_equal(part.mask, frame.bodies == part.body_id)
            assert abs(part.x_mm - frame.scene.geo.pe1_x) <= 150.0 + 1.0
            assert abs(part.y_mm) <= 80.0 + 1.0
    assert {p.cls for f in frames for p in f.parts} == {0, 1, 2}
