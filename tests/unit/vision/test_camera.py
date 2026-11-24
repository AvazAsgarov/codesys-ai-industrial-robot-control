"""Inspection camera model: projection, back-projection onto the belt, field of view."""

import numpy as np
import pytest

from airc.twin.config import TwinConfig
from airc.twin.twin import Twin
from airc.vision.camera import CameraModel

BELT_HALF_WIDTH_MM = 150.0
LARGEST_PART_MM = 120.0


@pytest.fixture(scope="module")
def twin() -> Twin:
    return Twin()


@pytest.fixture(scope="module")
def camera(twin: Twin) -> CameraModel:
    return CameraModel.from_mujoco(twin.model, twin.data, "cam_inspect")


def test_intrinsics_follow_fovy(camera: CameraModel) -> None:
    cfg = TwinConfig.load().camera
    assert (camera.width, camera.height) == (cfg.width_px, cfg.height_px)
    fy = (cfg.height_px / 2) / np.tan(np.radians(cfg.fovy_deg) / 2)
    assert camera.k[1, 1] == pytest.approx(fy)
    assert camera.k[0, 0] == pytest.approx(fy)
    assert camera.k[0, 2] == pytest.approx(cfg.width_px / 2)


def test_projection_round_trip(camera: CameraModel, twin: Twin) -> None:
    geo = twin.geo
    for x, y, z in [(300.0, 0.0, 0.0), (250.0, 100.0, 40.0), (380.0, -120.0, 70.0)]:
        world = (
            np.array([geo.belt_origin_x + x, geo.belt_origin_y + y, geo.belt_surface_z + z]) * 1e-3
        )
        u, v = camera.project(world)
        bx, by = camera.pixel_to_belt(u, v, z, geo)
        assert bx == pytest.approx(x, abs=0.1)
        assert by == pytest.approx(y, abs=0.1)


def test_frame_covers_belt_at_pe1(camera: CameraModel, twin: Twin) -> None:
    geo = twin.geo
    margin = LARGEST_PART_MM / 2
    for dx in (-margin, margin):
        for y in (-BELT_HALF_WIDTH_MM, BELT_HALF_WIDTH_MM):
            for z in (0.0, 90.0):
                world = np.array(
                    [geo.belt_origin_x + geo.pe1_x + dx, geo.belt_origin_y + y,
                     geo.belt_surface_z + z]
                ) * 1e-3  # fmt: skip
                u, v = camera.project(world)
                assert 0 <= u < camera.width, (dx, y, z, u)
                assert 0 <= v < camera.height, (dx, y, z, v)


def test_point_behind_the_camera_is_rejected(camera: CameraModel) -> None:
    behind = camera.position_m + camera.forward * -1.0
    with pytest.raises(ValueError, match="behind"):
        camera.project(behind)
