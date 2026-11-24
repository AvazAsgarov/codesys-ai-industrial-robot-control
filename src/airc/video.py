"""Video recorder for showcase videos of the running cell (``airc run --record``).

The bridge cycle only copies the twin's state (a few hundred floats) every ``1/fps`` seconds of
wall time and puts it on a bounded queue, dropping the frame when the queue is full rather than
waiting. A worker thread owns its own ``MjData`` and the OpenGL renderer, renders the chosen
camera, overlays a status banner and writes the frames to an mp4 file.
"""

import contextlib
import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from numpy.typing import NDArray

from airc.twin.scene import PART_GROUP
from airc.twin.twin import Twin

WIDTH_PX = 1280
HEIGHT_PX = 720
QUEUE_FRAMES = 30  # snapshots waiting for the renderer; more are dropped
STARTUP_TIMEOUT_S = 30.0
CLOSE_TIMEOUT_S = 60.0

cv: Any = cv2  # OpenCV's stubs leave its results untyped

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoSnapshot:
    """The twin's state for one video frame, plus the banner text."""

    t_s: float  # elapsed time shown in the banner
    qpos: NDArray[np.float64]
    qvel: NDArray[np.float64]
    mocap_pos: NDArray[np.float64]
    mocap_quat: NDArray[np.float64]
    state: str = ""  # PLC PackML state name
    placed: int | None = None  # parts in the bins so far

    @classmethod
    def of(
        cls, twin: Twin, t_s: float, state: str = "", placed: int | None = None
    ) -> "VideoSnapshot":
        """Copy what the renderer needs (cheap)."""
        d = twin.data
        return cls(
            t_s=t_s,
            qpos=d.qpos.copy(),
            qvel=d.qvel.copy(),
            mocap_pos=d.mocap_pos.copy(),
            mocap_quat=d.mocap_quat.copy(),
            state=state,
            placed=placed,
        )


def banner(snap: VideoSnapshot) -> str:
    """The status line drawn on a frame."""
    minutes, seconds = divmod(int(snap.t_s), 60)
    parts = [f"t {minutes:02d}:{seconds:02d}"]
    if snap.state:
        parts.append(snap.state)
    if snap.placed is not None:
        parts.append(f"placed {snap.placed}")
    return "   ".join(parts)


def _overlay(bgr: NDArray[np.uint8], text: str) -> None:
    font, scale, thick, pad = cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2, 10
    (w, h), base = cv.getTextSize(text, font, scale, thick)
    x1, y1 = int(w) + 2 * pad, int(h) + int(base) + 2 * pad
    bgr[:y1, :x1] = (bgr[:y1, :x1] * 0.4).astype(np.uint8)  # darkened box behind the text
    cv.putText(bgr, text, (pad, pad + int(h)), font, scale, (255, 255, 255), thick, cv2.LINE_AA)


class VideoRecorder:
    """Renders twin snapshots in its own thread and writes them to an mp4 file."""

    def __init__(
        self,
        twin: Twin,
        path: Path,
        fps: float = 10.0,
        camera: str = "cam_showcase",
        queue_size: int = QUEUE_FRAMES,
    ) -> None:
        """Open the file and start the renderer thread.

        Args:
            twin: The twin whose model is rendered (its data is never touched by the thread).
            path: The mp4 file (parent folders are created).
            fps: Frames per second, both of the snapshots (wall time) and of the video.
            camera: Camera of the scene to record (``cam_showcase`` or ``cam_inspect``).
            queue_size: Snapshots that may wait for the renderer before frames are dropped.

        Raises:
            ValueError: Unknown camera or a frame rate that is not positive.
            OSError: The video file cannot be opened.
            RuntimeError: The renderer cannot start (e.g. no OpenGL context).
        """
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        try:
            twin.model.camera(camera)
        except KeyError:
            raise ValueError(f"the scene has no camera {camera!r}") from None
        self._model = twin.model
        self._camera = camera
        self.fps = fps
        self.path = path
        self.frames_written = 0
        self.dropped = 0
        self.closed = False
        self._period_s = 1.0 / fps
        self._t0: float | None = None
        self._next_s = 0.0
        self._jobs: queue.Queue[VideoSnapshot | None] = queue.Queue(maxsize=queue_size)
        path.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv.VideoWriter_fourcc(*"mp4v")
        self._writer: Any = cv.VideoWriter(str(path), fourcc, fps, (WIDTH_PX, HEIGHT_PX))
        if not self._writer.isOpened():
            raise OSError(f"cannot open the video file {path}")
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, name="video", daemon=True)
        self._thread.start()
        if not self._ready.wait(STARTUP_TIMEOUT_S) or self._error is not None:
            self.closed = True
            self._writer.release()
            raise RuntimeError(f"video renderer did not start: {self._error!r}")

    def capture(self, twin: Twin, state: str = "", placed: int | None = None) -> bool:
        """Snapshot the twin if a frame is due (call every cycle; cheap when none is).

        Returns:
            Whether a snapshot was queued.
        """
        now = time.perf_counter()
        if self._t0 is None:
            self._t0 = self._next_s = now
        if now < self._next_s:
            return False
        self._next_s += self._period_s
        if self._next_s <= now:  # late (a long cycle): restart the schedule, no burst
            self._next_s = now + self._period_s
        return self.submit(VideoSnapshot.of(twin, now - self._t0, state, placed))

    def submit(self, snap: VideoSnapshot) -> bool:
        """Queue a frame (never blocks: drops it if the renderer is behind).

        Returns:
            Whether the frame was queued.
        """
        if self.closed:
            return False
        try:
            self._jobs.put_nowait(snap)
        except queue.Full:
            self.dropped += 1
            return False
        return True

    def close(self) -> None:
        """Render the queued frames, finish the file and stop the thread (idempotent)."""
        if self.closed:
            return
        self.closed = True
        with contextlib.suppress(queue.Full):
            self._jobs.put(None, timeout=CLOSE_TIMEOUT_S)
        self._thread.join(timeout=CLOSE_TIMEOUT_S)
        if self._thread.is_alive():
            _log.warning("video recorder did not finish in time: %s may be incomplete", self.path)
        if self.dropped:
            _log.info("video: %d frames written, %d dropped", self.frames_written, self.dropped)

    # --- worker thread ---------------------------------------------------------------------------
    def _run(self) -> None:
        try:
            renderer = mujoco.Renderer(self._model, HEIGHT_PX, WIDTH_PX)
        except Exception as exc:  # e.g. no OpenGL context
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        options = mujoco.MjvOption()
        options.geomgroup[:] = 0
        options.geomgroup[: PART_GROUP + 1] = 1  # the cell and the parts, not the calib board
        data = mujoco.MjData(self._model)
        try:
            while (snap := self._jobs.get()) is not None:
                try:
                    self._frame(renderer, options, data, snap)
                except Exception:  # a bad frame must not end the recording
                    _log.exception("video frame at %.1f s failed", snap.t_s)
        finally:
            renderer.close()
            self._writer.release()

    def _frame(
        self,
        renderer: mujoco.Renderer,
        options: mujoco.MjvOption,
        data: mujoco.MjData,
        snap: VideoSnapshot,
    ) -> None:
        data.qpos[:] = snap.qpos
        data.qvel[:] = snap.qvel
        data.mocap_pos[:] = snap.mocap_pos
        data.mocap_quat[:] = snap.mocap_quat
        mujoco.mj_forward(self._model, data)
        renderer.update_scene(data, camera=self._camera, scene_option=options)
        rgb = renderer.render()
        bgr: NDArray[np.uint8] = np.ascontiguousarray(rgb[:, :, ::-1])
        _overlay(bgr, banner(snap))
        self._writer.write(bgr)
        self.frames_written += 1
