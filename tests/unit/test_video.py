"""Video recorder: renders twin snapshots in its own thread and writes an mp4."""

import time
from pathlib import Path

import cv2
import pytest

from airc.twin.twin import Twin
from airc.video import VideoRecorder, VideoSnapshot

pytestmark = pytest.mark.render


def _recorder(twin: Twin, path: Path, **kwargs: object) -> VideoRecorder:
    try:
        return VideoRecorder(twin, path, **kwargs)  # type: ignore[arg-type]
    except RuntimeError as exc:  # no OpenGL context on this machine (e.g. a headless CI runner)
        pytest.skip(f"no OpenGL context: {exc}")


def _frames(path: Path) -> tuple[int, int, int]:
    cap = cv2.VideoCapture(str(path))
    count, size = 0, (0, 0)
    while True:
        ok, img = cap.read()
        if not ok:
            break
        count += 1
        size = (img.shape[1], img.shape[0])
    cap.release()
    return count, size[0], size[1]


def test_snapshots_become_mp4_frames(tmp_path: Path) -> None:
    twin = Twin()
    path = tmp_path / "out" / "demo.mp4"
    rec = _recorder(twin, path, fps=10.0)
    for i in range(5):
        assert rec.submit(VideoSnapshot.of(twin, t_s=i / 10, state="EXECUTE", placed=i))
        time.sleep(0.15)  # let the worker keep up: no frame dropped
    rec.close()
    assert path.is_file()
    assert path.stat().st_size > 0
    count, width, height = _frames(path)
    assert count >= 5
    assert (width, height) == (1280, 720)
    assert rec.frames_written == 5
    assert rec.dropped == 0


def test_full_queue_drops_frames_instead_of_blocking(tmp_path: Path) -> None:
    twin = Twin()
    rec = _recorder(twin, tmp_path / "drop.mp4", fps=10.0)
    snap = VideoSnapshot.of(twin, t_s=0.0)
    t0 = time.perf_counter()
    accepted = [rec.submit(snap) for _ in range(200)]
    elapsed = time.perf_counter() - t0
    rec.close()
    assert elapsed < 0.1  # 200 renders would take seconds: submit never waits for the worker
    assert not all(accepted)
    assert rec.dropped == accepted.count(False)
    assert rec.frames_written == accepted.count(True)


def test_capture_snapshots_at_the_frame_rate(tmp_path: Path) -> None:
    twin = Twin()
    rec = _recorder(twin, tmp_path / "rate.mp4", fps=10.0)
    t0 = time.perf_counter()
    taken = 0
    while time.perf_counter() - t0 < 0.55:  # 20 ms cycles for 0.55 s
        taken += rec.capture(twin, state="EXECUTE", placed=0)
        time.sleep(0.02)
    rec.close()
    assert 5 <= taken <= 7  # t = 0, 0.1, ..., 0.5 s


def test_close_is_idempotent_and_later_submits_are_ignored(tmp_path: Path) -> None:
    twin = Twin()
    rec = _recorder(twin, tmp_path / "closed.mp4")
    rec.close()
    rec.close()
    assert not rec.submit(VideoSnapshot.of(twin, t_s=0.0))


def test_unknown_camera_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no_such_cam"):
        VideoRecorder(Twin(), tmp_path / "x.mp4", camera="no_such_cam")
