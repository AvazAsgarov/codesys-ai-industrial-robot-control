"""Offscreen rendering of the inspection camera (needs an OpenGL context; marked render)."""

import numpy as np
import pytest

from airc.twin.config import TwinConfig
from airc.twin.twin import PartSpec, Twin
from airc.vision.camera import CameraModel
from airc.vision.render import FrameRenderer, Randomisation

pytestmark = pytest.mark.render


@pytest.fixture(scope="module")
def setup() -> tuple[Twin, FrameRenderer]:
    twin = Twin(cfg=TwinConfig.load(parts="catalogue"))
    try:
        renderer = FrameRenderer(twin.model, "cam_inspect")
    except Exception as exc:  # no OpenGL context on this machine (e.g. a headless CI runner)
        pytest.skip(f"no OpenGL context: {exc}")
    return twin, renderer


def test_render_shapes_and_part_masks(setup: tuple[Twin, FrameRenderer]) -> None:
    twin, renderer = setup
    pid = twin.spawn(PartSpec(cls=1, y_mm=30.0, theta_deg=15.0, x_mm=twin.geo.pe1_x))
    twin.step(twin.joint_positions_rad(), 0.0, 0.0, False)
    frame = renderer.render(twin.data)
    cfg = twin.cfg.camera
    assert frame.rgb.shape == (cfg.height_px, cfg.width_px, 3)
    assert frame.rgb.dtype == np.uint8
    mask = frame.body_mask(twin.part_body_id(pid))
    assert mask.sum() > 2000  # the part is clearly visible
    assert not mask[0, :].any()  # inside the frame
    assert not mask[-1, :].any()


def test_part_mask_centroid_maps_to_its_belt_position(setup: tuple[Twin, FrameRenderer]) -> None:
    twin, renderer = setup
    camera = CameraModel.from_mujoco(twin.model, twin.data, "cam_inspect")
    pid = twin.spawn(PartSpec(cls=1, y_mm=-40.0, theta_deg=0.0, x_mm=twin.geo.pe1_x - 20.0))
    twin.step(twin.joint_positions_rad(), 0.0, 0.0, False)
    frame = renderer.render(twin.data)
    vs, us = np.nonzero(frame.body_mask(twin.part_body_id(pid)))
    part = twin.part(pid)
    height = twin.cfg.parts.classes[1].height_mm
    x, y = camera.pixel_to_belt(float(us.mean()), float(vs.mean()), height / 2, twin.geo)
    assert x == pytest.approx(part.x_mm, abs=15.0)  # silhouette centroid vs body origin
    assert y == pytest.approx(part.y_mm, abs=15.0)


def test_randomisation_is_seeded_and_keeps_masks(setup: tuple[Twin, FrameRenderer]) -> None:
    twin, renderer = setup
    rand_a = Randomisation.draw(np.random.default_rng(7))
    rand_b = Randomisation.draw(np.random.default_rng(7))
    assert rand_a == rand_b
    plain = renderer.render(twin.data)
    varied = renderer.render(twin.data, rand_a)
    assert not np.array_equal(plain.rgb, varied.rgb)
    assert np.array_equal(plain.bodies, varied.bodies)  # ground truth does not change
