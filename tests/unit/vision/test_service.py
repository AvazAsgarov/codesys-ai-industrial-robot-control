"""Vision worker: answers PLC captures from rendered frames in its own thread."""

import time
from collections.abc import Callable, Iterator

import numpy as np
import pytest
from numpy.typing import NDArray

from airc.bridge.messages import CaptureMsg
from airc.twin.config import TwinConfig
from airc.twin.twin import PartSpec, Twin
from airc.vision.detector import Detection
from airc.vision.render import Frame
from airc.vision.service import CaptureJob, VisionResult, VisionWorker

pytestmark = pytest.mark.render


class OracleDetector:
    """Returns the true masks of the parts in the image (tests the geometry, not the model)."""

    name = "oracle"

    def __init__(self, twin: Twin) -> None:
        self.twin = twin
        self.bodies: NDArray[np.int32] | None = None  # set by the worker hook below
        self.calls = 0
        self.fail_next = False
        self.delay_s = 0.0

    def detect(self, rgb: NDArray[np.uint8]) -> list[Detection]:
        del rgb  # the oracle uses the true masks
        self.calls += 1
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("detector crashed")
        assert self.bodies is not None
        out: list[Detection] = []
        for part in self.twin.parts():
            mask = self.bodies == self.twin.part_body_id(part.pid)
            if mask.sum() > 50:
                vs, us = np.nonzero(mask)
                box = (float(us.min()), float(vs.min()), float(us.max()), float(vs.max()))
                out.append(Detection("part", part.cls, 0.9, box, mask))
        return out


def _wait(worker: VisionWorker, n: int, timeout_s: float = 20.0) -> list[VisionResult]:
    got: list[VisionResult] = []
    deadline = time.monotonic() + timeout_s
    while len(got) < n and time.monotonic() < deadline:
        got += worker.poll()
        time.sleep(0.01)
    return got


Build = Callable[[], tuple[Twin, OracleDetector, VisionWorker]]


@pytest.fixture
def make() -> Iterator[Build]:
    workers: list[VisionWorker] = []

    def build() -> tuple[Twin, OracleDetector, VisionWorker]:
        twin = Twin(cfg=TwinConfig.load(parts="catalogue"))
        det = OracleDetector(twin)

        def hook(frame: Frame) -> None:
            det.bodies = frame.bodies

        worker = VisionWorker(twin, lambda: det, frame_hook=hook)
        workers.append(worker)
        return twin, det, worker

    yield build
    for w in workers:
        w.close()


def _job(twin: Twin, part_id: int, seq: int, capture_pos: float = 0.0) -> CaptureJob:
    return CaptureJob.snapshot(twin, CaptureMsg(seq, part_id, capture_pos), belt_pos_mm=capture_pos)


def test_capture_picks_the_part_at_pe1(make: Build) -> None:
    twin, _, worker = make()
    pe1 = twin.geo.pe1_x
    at_pe1 = twin.spawn(PartSpec(cls=1, y_mm=35.0, theta_deg=20.0, x_mm=pe1 + 10.0))
    twin.spawn(PartSpec(cls=0, y_mm=-60.0, theta_deg=0.0, x_mm=pe1 - 170.0))  # the next one
    twin.step(twin.joint_positions_rad(), 0.0, 0.0, False)
    worker.submit(_job(twin, 7, 1))
    [res] = _wait(worker, 1)
    truth = twin.part(at_pe1)
    assert res.msg.part_id == 7
    assert res.msg.valid
    assert res.msg.cls == 1
    assert res.msg.x_mm == pytest.approx(truth.x_mm, abs=8.0)
    assert res.msg.y_mm == pytest.approx(truth.y_mm, abs=8.0)
    assert res.latency_ms > 0
    assert res.crop.shape[2] == 3


def test_no_detection_gives_invalid_message(make: Build) -> None:
    twin, _, worker = make()
    worker.submit(_job(twin, 3, 1))  # nothing on the belt
    [res] = _wait(worker, 1)
    assert res.msg.part_id == 3
    assert not res.msg.valid


def test_worker_survives_detector_error(make: Build) -> None:
    twin, det, worker = make()
    twin.spawn(PartSpec(cls=2, y_mm=0.0, theta_deg=0.0, x_mm=twin.geo.pe1_x))
    twin.step(twin.joint_positions_rad(), 0.0, 0.0, False)
    det.fail_next = True
    worker.submit(_job(twin, 1, 1))
    worker.submit(_job(twin, 2, 2))
    first, second = _wait(worker, 2)
    assert (first.msg.part_id, first.msg.valid) == (1, False)
    assert (second.msg.part_id, second.msg.valid) == (2, True)
    assert first.error is not None


def test_late_result_keeps_its_part_id(make: Build) -> None:
    twin, det, worker = make()
    twin.spawn(PartSpec(cls=0, y_mm=0.0, theta_deg=0.0, x_mm=twin.geo.pe1_x))
    twin.step(twin.joint_positions_rad(), 0.0, 0.0, False)
    det.delay_s = 0.3
    worker.submit(_job(twin, 11, 1))
    worker.submit(_job(twin, 12, 2))
    results = _wait(worker, 2)
    assert [r.msg.part_id for r in results] == [11, 12]
    assert results[0].msg.seq != results[1].msg.seq
