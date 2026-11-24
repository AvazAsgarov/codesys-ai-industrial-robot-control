"""Checkerboard calibration of the inspection camera, compared with the exact MuJoCo camera.

Spec §6.1: the camera model is known from the MJCF, but the cell calibrates it the way a real
one would - a checkerboard (9 x 6 inner corners, 25 mm squares) shown in many poses gives the
intrinsics (OpenCV), and the board lying flat at a known place on the belt gives the camera's
pose. The result is compared with the truth (a paper result) and saved for the vision service.

OpenCV's camera frame is x right, y down, z forward; MuJoCo's is x right, y up, -z forward.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import cv2
import mujoco
import numpy as np
from numpy.typing import NDArray

from airc.twin.scene import CALIB_PARK, CALIB_SQUARE_M, CALIB_SQUARES, CALIB_TOP_M, MM
from airc.twin.twin import Twin
from airc.vision.camera import CameraModel
from airc.vision.render import FrameRenderer

FloatArray = NDArray[np.float64]
cv: Any = cv2  # OpenCV's stubs leave its results untyped; checked at the boundary here
CV_TO_MJ = np.diag([1.0, -1.0, -1.0])  # camera axes: OpenCV -> MuJoCo (and back)
_SUBPIX = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 1e-4)


@dataclass(frozen=True)
class Checkerboard:
    """Inner-corner grid of the board; object points have their origin at the board centre."""

    cols: int = CALIB_SQUARES[0] - 1
    rows: int = CALIB_SQUARES[1] - 1
    square_mm: float = CALIB_SQUARE_M * 1000.0

    def object_points(self) -> FloatArray:
        """Corner coordinates (m) in the board plane (z = 0), row by row (x fastest)."""
        s = self.square_mm * MM
        xs = (np.arange(self.cols) - (self.cols - 1) / 2) * s
        ys = (np.arange(self.rows) - (self.rows - 1) / 2) * s
        gx, gy = np.meshgrid(xs, ys)
        return np.column_stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)]).astype(np.float64)


@dataclass(frozen=True)
class Intrinsics:
    """Calibrated intrinsics and the RMS reprojection error of the calibration."""

    k: FloatArray
    dist: FloatArray
    rms_px: float


@dataclass(frozen=True)
class Calibration:
    """Result of :func:`run_calibration`."""

    camera: CameraModel
    rms_px: float
    dist: FloatArray
    views: int


@dataclass(frozen=True)
class CalibrationReport:
    """Calibrated camera vs. the exact one."""

    focal_error_pct: float
    principal_point_error_px: float
    position_error_mm: float
    rotation_error_deg: float


def calibrate_intrinsics(
    views: Sequence[FloatArray], board: Checkerboard, size: tuple[int, int]
) -> Intrinsics:
    """Intrinsics from detected corners (one (N, 2) pixel array per view).

    Tangential distortion and k3 are fixed at zero: the lens is close to a pinhole, and the free
    parameters would only fit noise.
    """
    obj = board.object_points().astype(np.float32)
    flags = cv2.CALIB_ZERO_TANGENT_DIST | cv2.CALIB_FIX_K3
    result: Any = cv.calibrateCamera(
        [obj for _ in views],
        [np.asarray(v, dtype=np.float32).reshape(-1, 1, 2) for v in views],
        size,
        None,
        None,
        flags=flags,
    )
    rms, k, dist = float(result[0]), np.asarray(result[1]), np.asarray(result[2])
    return Intrinsics(k=k.astype(np.float64), dist=dist.ravel().astype(np.float64), rms_px=rms)


def camera_to_world(
    r_cb: FloatArray, t_cb: FloatArray, r_wb: FloatArray, t_wb: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """Camera position and OpenCV axes in world.

    From the board's pose in the camera (``r_cb``, ``t_cb``: board -> camera) and in the world
    (``r_wb``, ``t_wb``).
    """
    position_in_board = -r_cb.T @ t_cb
    position = r_wb @ position_in_board + t_wb
    r_wc_cv = r_wb @ r_cb.T
    return position, r_wc_cv


def compare(calibrated: CameraModel, truth: CameraModel) -> CalibrationReport:
    """Errors of the calibrated camera against the exact one."""
    focal = (calibrated.k[0, 0] + calibrated.k[1, 1]) / (truth.k[0, 0] + truth.k[1, 1]) - 1.0
    pp = float(np.hypot(*(calibrated.k[:2, 2] - truth.k[:2, 2])))
    rel = calibrated.r_wc.T @ truth.r_wc
    angle = float(np.degrees(np.arccos(np.clip((np.trace(rel) - 1.0) / 2.0, -1.0, 1.0))))
    return CalibrationReport(
        focal_error_pct=float(focal * 100.0),
        principal_point_error_px=pp,
        position_error_mm=float(np.linalg.norm(calibrated.position_m - truth.position_m) / MM),
        rotation_error_deg=angle,
    )


def _rot(rx: float, ry: float, rz: float) -> FloatArray:
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return mz @ my @ mx


def _quat(r: FloatArray) -> FloatArray:
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, r.ravel())
    return q


class _Board:
    """Moves the twin's calibration board (a mocap body)."""

    def __init__(self, twin: Twin) -> None:
        self.twin = twin
        self.mocap = int(twin.model.body_mocapid[twin.model.body("calib_board").id])

    def place(self, centre_m: FloatArray, r_wb: FloatArray) -> FloatArray:
        """Put the board surface centre at ``centre_m`` with axes ``r_wb``.

        Returns the body position (the surface is ``CALIB_TOP_M`` above it along the normal).
        """
        body = centre_m - r_wb[:, 2] * CALIB_TOP_M
        self.twin.data.mocap_pos[self.mocap] = body
        self.twin.data.mocap_quat[self.mocap] = _quat(r_wb)
        mujoco.mj_forward(self.twin.model, self.twin.data)
        return body

    def park(self) -> None:
        self.twin.data.mocap_pos[self.mocap] = np.array(CALIB_PARK)
        mujoco.mj_forward(self.twin.model, self.twin.data)


def _corners(rgb: NDArray[np.uint8], board: Checkerboard) -> FloatArray | None:
    gray: Any = cv.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    found, corners = cv.findChessboardCorners(gray, (board.cols, board.rows))
    if not found:
        return None
    refined: Any = cv.cornerSubPix(gray, corners, (5, 5), (-1, -1), _SUBPIX)
    return np.asarray(refined, dtype=np.float64).reshape(-1, 2)


def run_calibration(twin: Twin, poses: int = 15, seed: int = 7) -> Calibration:
    """Calibrate ``cam_inspect`` from rendered views of the board (seeded poses).

    Raises:
        RuntimeError: If no OpenGL context can be created, or too few views were detected.
    """
    try:
        renderer = FrameRenderer(twin.model, "cam_inspect", twin.cfg)
    except Exception as exc:
        msg = f"no OpenGL context for rendering: {exc}"
        raise RuntimeError(msg) from exc
    board = Checkerboard()
    holder = _Board(twin)
    geo = twin.geo
    pe1 = np.array([geo.belt_origin_x + geo.pe1_x, geo.belt_origin_y, geo.belt_surface_z]) * MM
    rng = np.random.default_rng(seed)
    views: list[FloatArray] = []
    try:
        attempts = 0
        while len(views) < poses and attempts < 4 * poses:
            attempts += 1
            r_wb = _rot(*np.radians(rng.uniform([-25, -25, -20], [25, 25, 20])))
            centre = pe1 + np.array(
                [rng.uniform(-0.08, 0.08), rng.uniform(-0.05, 0.05), rng.uniform(0.05, 0.20)]
            )
            holder.place(centre, r_wb)
            corners = _corners(renderer.render(twin.data).rgb, board)
            if corners is not None:
                views.append(corners)
        if len(views) < max(5, poses // 2):
            msg = f"only {len(views)} of {attempts} board views were detected"
            raise RuntimeError(msg)
        cam = twin.cfg.camera
        intr = calibrate_intrinsics(views, board, (cam.width_px, cam.height_px))
        # extrinsics: the board lying flat at photo-eye PE1, its x along the belt
        r_wb = np.eye(3)
        t_wb = pe1 + np.array([0.0, 0.0, CALIB_TOP_M + 0.0005])
        holder.place(t_wb, r_wb)
        corners = _corners(renderer.render(twin.data).rgb, board)
        if corners is None:
            msg = "the reference board on the belt was not detected"
            raise RuntimeError(msg)
        position, r_wc_cv = _reference_pose(corners, board, intr, r_wb, t_wb)
    finally:
        holder.park()
        renderer.close()
    camera = CameraModel(
        k=intr.k,
        r_wc=r_wc_cv @ CV_TO_MJ,
        position_m=position,
        width=twin.cfg.camera.width_px,
        height=twin.cfg.camera.height_px,
    )
    return Calibration(camera=camera, rms_px=intr.rms_px, dist=intr.dist, views=len(views))


def _reference_pose(
    corners: FloatArray, board: Checkerboard, intr: Intrinsics, r_wb: FloatArray, t_wb: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """Camera pose from the board at a known place.

    OpenCV may list the corners from any corner of the grid; the board lies with its x along the
    belt (image right) and faces the camera, which settles the order.
    """
    obj = board.object_points().astype(np.float32)
    grid = corners.reshape(board.rows, board.cols, 2)
    orders = (grid, grid[::-1, ::-1], grid[::-1, :], grid[:, ::-1])
    best: tuple[float, FloatArray, FloatArray] | None = None
    for order in orders:
        candidate = order.reshape(-1, 1, 2).astype(np.float32)
        ok, rvec, tvec = cv.solvePnP(obj, candidate, intr.k, intr.dist)
        if not ok:
            continue
        r_cb = np.asarray(cv.Rodrigues(rvec)[0], dtype=np.float64)
        if not (r_cb[0, 0] > 0 and r_cb[2, 2] < 0):  # x to the right, facing the camera
            continue
        projected = np.asarray(cv.projectPoints(obj, rvec, tvec, intr.k, intr.dist)[0])
        error = float(np.sqrt(np.mean((projected.reshape(-1, 2) - order.reshape(-1, 2)) ** 2)))
        if best is None or error < best[0]:
            position, r_wc_cv = camera_to_world(
                r_cb, np.asarray(tvec, dtype=np.float64).ravel(), r_wb, t_wb
            )
            best = (error, position, r_wc_cv)
    if best is None:
        msg = "could not resolve the reference board's orientation"
        raise RuntimeError(msg)
    return best[1], best[2]
