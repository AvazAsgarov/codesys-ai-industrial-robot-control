"""Vision service: answers the PLC's capture requests from rendered camera frames.

The runner snapshots the twin when the PLC asks for a capture and submits it; a worker thread
renders the inspection camera at that instant, detects the parts in a region of interest
around photo-eye PE1, turns the chosen part's mask into its belt pose through the (calibrated)
camera model and hands back a :class:`VisionMsg`. The bridge cycle never waits for it.
"""

import contextlib
import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import mujoco
import numpy as np
from numpy.typing import NDArray

from airc.bridge.messages import CaptureMsg, VisionMsg
from airc.twin.cell import CellGeometry
from airc.twin.config import TwinConfig
from airc.twin.twin import Twin
from airc.vision.camera import CameraModel
from airc.vision.detector import Detection, Detector
from airc.vision.pose import mask_pose
from airc.vision.render import Frame, FrameRenderer

MAX_DISTANCE_MM = 150.0  # a detection farther from PE1 (at capture) is not the captured part
ROI_PX = 640  # detector input: a native-resolution window around PE1
AXIS_PX = 30.0  # half length of the image segment that turns theta into the belt frame
CROP_MARGIN = 0.10  # crop of the chosen part (for THX-02 in Phase 4): box + 10 %
CALIBRATED = Path("config/calibration/cam_inspect.json")

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureJob:
    """The twin's state at a capture request."""

    capture: CaptureMsg
    belt_pos_mm: float  # conveyor position when the snapshot was taken
    qpos: NDArray[np.float64]
    qvel: NDArray[np.float64]
    mocap_pos: NDArray[np.float64]
    mocap_quat: NDArray[np.float64]
    truth: list[tuple[int, int, float, float, float]] = field(
        default_factory=list[tuple[int, int, float, float, float]]
    )  # (pid, cls, x, y, theta) of the parts on the belt

    @classmethod
    def snapshot(cls, twin: Twin, capture: CaptureMsg, belt_pos_mm: float) -> "CaptureJob":
        """Copy what the renderer needs (cheap: a few hundred floats)."""
        d = twin.data
        truth = [(p.pid, p.cls, p.x_mm, p.y_mm, p.theta_deg) for p in twin.parts() if p.on_belt]
        return cls(
            capture=capture,
            belt_pos_mm=belt_pos_mm,
            qpos=d.qpos.copy(),
            qvel=d.qvel.copy(),
            mocap_pos=d.mocap_pos.copy(),
            mocap_quat=d.mocap_quat.copy(),
            truth=truth,
        )


@dataclass(frozen=True)
class VisionResult:
    """The answer to one capture, with what the evaluation needs."""

    msg: VisionMsg
    latency_ms: float
    detections: int
    crop: NDArray[np.uint8]  # the chosen part (empty if none)
    error: str | None = None
    job: CaptureJob | None = None


def _wrap_theta(deg: float) -> float:
    return (deg + 90.0) % 180.0 - 90.0


Roi = tuple[slice, slice]  # rows, columns of the full camera image


def pe1_roi(camera: CameraModel, geo: CellGeometry, cfg: TwinConfig) -> Roi:
    """The detector's window: ``ROI_PX`` square, native resolution, centred on PE1 if it fits.

    The centre is where the camera sees PE1 on the belt's centre line at half the mean part
    height; the window is shifted inside the image where it would cross the border.
    """
    heights = [c.height_mm for c in cfg.parts.classes]
    pe1 = (
        np.array(
            [
                geo.belt_origin_x + geo.pe1_x,
                geo.belt_origin_y,
                geo.belt_surface_z + np.mean(heights) / 2,
            ]
        )
        * 1e-3
    )
    u, v = camera.project(pe1)
    half = ROI_PX // 2
    cam = cfg.camera
    u0 = max(int(min(max(round(u) - half, 0), cam.width_px - ROI_PX)), 0)
    v0 = max(int(min(max(round(v) - half, 0), cam.height_px - ROI_PX)), 0)
    return slice(v0, v0 + ROI_PX), slice(u0, u0 + ROI_PX)


def crop_roi(frame: Frame, roi: Roi) -> Frame:
    """The window ``roi`` of a full camera frame (contiguous copies)."""
    return Frame(
        rgb=np.ascontiguousarray(frame.rgb[roi]),
        bodies=np.ascontiguousarray(frame.bodies[roi]),
    )


@dataclass(frozen=True)
class BeltPose:
    """A detection's pose on the belt (belt frame) and its image pose in the full frame."""

    x_mm: float
    y_mm: float
    theta_deg: float  # belt frame, wrapped to [-90, 90)
    u: float  # mask centroid in the full image
    v: float
    z_mm: float  # height above the belt of the plane the centroid is mapped onto


def belt_pose(
    det: Detection, roi: Roi, camera: CameraModel, geo: CellGeometry, heights_mm: list[float]
) -> BeltPose:
    """Pixel -> belt pose of a detection found in the window ``roi``.

    The mask centroid is mapped onto the plane at half the class height (the mean height for a
    detection without class); the mask's principal axis is mapped through two points along it.

    Raises:
        ValueError: If the mask is empty.
    """
    pose = mask_pose(det.mask)
    u = pose.u + roi[1].start
    v = pose.v + roi[0].start
    z = (heights_mm[det.cls] if det.cls is not None else float(np.mean(heights_mm))) / 2
    x, y = camera.pixel_to_belt(u, v, z, geo)
    t = np.radians(pose.theta_deg)
    du, dv = AXIS_PX * np.cos(t), -AXIS_PX * np.sin(t)  # image v points down
    x1, y1 = camera.pixel_to_belt(u - du, v - dv, z, geo)
    x2, y2 = camera.pixel_to_belt(u + du, v + dv, z, geo)
    theta = _wrap_theta(float(np.degrees(np.arctan2(y2 - y1, x2 - x1))))
    return BeltPose(x, y, theta, u, v, z)


class VisionWorker:
    """A thread that owns the renderer and the detector (OpenGL and OpenVINO stay in it)."""

    def __init__(
        self,
        twin: Twin,
        detector_factory: Callable[[], Detector],
        camera: CameraModel | None = None,
        frame_hook: Callable[[Frame], None] | None = None,
    ) -> None:
        """Start the worker.

        Args:
            twin: The twin whose model is rendered (its data is never touched).
            detector_factory: Creates the detector inside the worker thread.
            camera: Camera model for pixel -> belt; default: the calibrated one
                (``config/calibration/cam_inspect.json``) if present, else the exact model.
            frame_hook: Test hook, called with each detector input (region of interest).
        """
        self._twin = twin
        self._factory = detector_factory
        self._hook = frame_hook
        self._camera = camera if camera is not None else self._default_camera(twin)
        self._jobs: queue.Queue[CaptureJob | None] = queue.Queue()
        self._done: queue.Queue[VisionResult] = queue.Queue()
        self._seq = 0
        self._heights = [c.height_mm for c in twin.cfg.parts.classes]
        self._roi = pe1_roi(self._camera, twin.geo, twin.cfg)
        self._thread = threading.Thread(target=self._run, name="vision", daemon=True)
        self._thread.start()

    @staticmethod
    def _default_camera(twin: Twin) -> CameraModel:
        from airc.vision.models import repo_root  # noqa: PLC0415

        path = repo_root() / CALIBRATED
        if path.is_file():
            return CameraModel.load(path)
        return CameraModel.from_mujoco(twin.model, twin.data, "cam_inspect")

    def submit(self, job: CaptureJob) -> None:
        """Queue a capture (returns at once)."""
        self._jobs.put(job)

    def poll(self) -> list[VisionResult]:
        """Results finished since the last poll, in submission order (never blocks)."""
        out: list[VisionResult] = []
        with contextlib.suppress(queue.Empty):
            while True:
                out.append(self._done.get_nowait())
        return out

    def close(self) -> None:
        """Stop the thread (pending jobs are dropped)."""
        self._jobs.put(None)
        self._thread.join(timeout=10.0)

    # --- worker thread ---------------------------------------------------------------------------
    def _run(self) -> None:
        model = self._twin.model
        data = mujoco.MjData(model)
        renderer: FrameRenderer | None = None
        detector: Detector | None = None
        while True:
            job = self._jobs.get()
            if job is None:
                break
            t0 = time.perf_counter()
            self._seq += 1
            try:
                if renderer is None:
                    renderer = FrameRenderer(model, "cam_inspect", self._twin.cfg)
                if detector is None:
                    detector = self._factory()
                data.qpos[:] = job.qpos
                data.qvel[:] = job.qvel
                data.mocap_pos[:] = job.mocap_pos
                data.mocap_quat[:] = job.mocap_quat
                mujoco.mj_forward(model, data)
                frame = renderer.render(data)
                result = self._answer(job, frame, detector, t0)
            except Exception as exc:  # the cell must keep running: answer "not seen"
                _log.exception("vision failed for part %s", job.capture.part_id)
                result = VisionResult(
                    msg=self._invalid(job),
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    detections=0,
                    crop=np.zeros((0, 0, 3), dtype=np.uint8),
                    error=repr(exc),
                    job=job,
                )
            self._done.put(result)
        if renderer is not None:
            renderer.close()

    def _invalid(self, job: CaptureJob) -> VisionMsg:
        return VisionMsg(self._seq, job.capture.part_id, False, 0, 0.0, 0.0, 0.0, 0.0)

    def _answer(self, job: CaptureJob, frame: Frame, detector: Detector, t0: float) -> VisionResult:
        roi = crop_roi(frame, self._roi)
        if self._hook is not None:
            self._hook(roi)
        detections = detector.detect(roi.rgb)
        travel = job.belt_pos_mm - job.capture.belt_pos_mm
        pe1 = self._twin.geo.pe1_x
        best: tuple[float, Detection, float, float, float] | None = None
        for det in detections:
            pose = belt_pose(det, self._roi, self._camera, self._twin.geo, self._heights)
            distance = abs(pose.x_mm - travel - pe1)
            if distance > MAX_DISTANCE_MM:
                continue
            key = distance + (0.0 if det.cls is not None else 1e6)  # a part before anything else
            if best is None or key < best[0]:
                best = (key, det, pose.x_mm - travel, pose.y_mm, pose.theta_deg)
        latency = (time.perf_counter() - t0) * 1000.0
        if best is None or best[1].cls is None:
            return VisionResult(
                self._invalid(job), latency, len(detections), np.zeros((0, 0, 3), np.uint8), job=job
            )
        _, det, x, y, theta = best
        assert det.cls is not None
        msg = VisionMsg(
            seq=self._seq,
            part_id=job.capture.part_id,
            valid=True,
            cls=det.cls,
            confidence=det.confidence,
            x_mm=x,
            y_mm=y,
            theta_deg=theta,
        )
        return VisionResult(msg, latency, len(detections), self._crop(roi.rgb, det), job=job)

    @staticmethod
    def _crop(rgb: NDArray[np.uint8], det: Detection) -> NDArray[np.uint8]:
        x0, y0, x1, y1 = det.box_xyxy
        mx, my = (x1 - x0) * CROP_MARGIN, (y1 - y0) * CROP_MARGIN
        h, w = rgb.shape[:2]
        r0, r1 = max(int(y0 - my), 0), min(int(y1 + my) + 1, h)
        c0, c1 = max(int(x0 - mx), 0), min(int(x1 + mx) + 1, w)
        return rgb[r0:r1, c0:c1].copy()
