"""Checkerboard calibration of the inspection camera, compared with the exact MuJoCo camera."""

import numpy as np
import pytest

from airc.twin.twin import Twin
from airc.vision.calibration import (
    Checkerboard,
    calibrate_intrinsics,
    camera_to_world,
    compare,
    run_calibration,
)
from airc.vision.camera import CameraModel


def test_board_object_points_are_a_grid_in_metres() -> None:
    board = Checkerboard(cols=9, rows=6, square_mm=25.0)
    pts = board.object_points()
    assert pts.shape == (54, 3)
    assert pts[1, 0] - pts[0, 0] == pytest.approx(0.025)
    assert pts[9, 1] - pts[0, 1] == pytest.approx(0.025)
    assert np.allclose(pts.mean(axis=0), 0.0)  # origin at the board centre


def test_intrinsics_recovered_from_synthetic_corners() -> None:
    board = Checkerboard(cols=9, rows=6, square_mm=25.0)
    k_true = np.array([[870.0, 0.0, 640.0], [0.0, 870.0, 360.0], [0.0, 0.0, 1.0]])
    rng = np.random.default_rng(3)
    views: list[np.ndarray] = []
    for _ in range(12):  # boards 0.5-0.8 m in front of the camera, tilted up to 45 deg
        rvec = rng.uniform(-0.8, 0.8, 3)  # well tilted views separate focal length and distance
        tvec = np.array([rng.uniform(-0.1, 0.1), rng.uniform(-0.05, 0.05), rng.uniform(0.5, 0.8)])
        r = _rodrigues(rvec)
        cam = (r @ board.object_points().T).T + tvec
        uv = (k_true @ cam.T).T
        views.append(uv[:, :2] / uv[:, 2:] + rng.normal(0.0, 0.2, (len(cam), 2)))
    result = calibrate_intrinsics(views, board, (1280, 720))
    assert result.rms_px < 0.5
    assert result.k[0, 0] == pytest.approx(870.0, rel=0.005)
    assert result.k[1, 1] == pytest.approx(870.0, rel=0.005)


def test_camera_to_world_inverts_the_pose() -> None:
    truth_r = _rodrigues(np.array([0.3, -0.2, 0.1]))
    truth_c = np.array([0.4, -0.3, 0.9])
    # a board pose in world, and the camera's view of it (OpenCV convention)
    r_wb = _rodrigues(np.array([0.0, 0.0, 0.4]))
    t_wb = np.array([-1.0, -0.5, 0.05])
    r_cv_w = truth_r.T  # world -> OpenCV camera, with camera axes truth_r in world
    r_cb = r_cv_w @ r_wb
    t_cb = r_cv_w @ (t_wb - truth_c)
    position, r_wc_cv = camera_to_world(r_cb, t_cb, r_wb, t_wb)
    assert np.allclose(position, truth_c, atol=1e-9)
    assert np.allclose(r_wc_cv, truth_r, atol=1e-9)


@pytest.mark.render
def test_rendered_calibration_matches_the_exact_camera() -> None:
    twin = Twin()
    truth = CameraModel.from_mujoco(twin.model, twin.data, "cam_inspect")
    try:
        cal = run_calibration(twin, poses=15, seed=7)
    except RuntimeError as exc:  # no OpenGL context on this machine
        pytest.skip(str(exc))
    report = compare(cal.camera, truth)
    assert cal.rms_px < 0.5
    assert abs(report.focal_error_pct) < 1.0
    assert report.position_error_mm < 5.0
    assert report.rotation_error_deg < 0.5


def _rodrigues(rvec: np.ndarray) -> np.ndarray:
    theta = float(np.linalg.norm(rvec))
    if theta < 1e-12:
        return np.eye(3)
    k = rvec / theta
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(theta) * kx + (1 - np.cos(theta)) * kx @ kx
