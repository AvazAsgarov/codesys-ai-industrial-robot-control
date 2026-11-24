"""DecisionWorker: decisions in their own thread and event loop, never raising to the caller."""

import time

import numpy as np
import pytest
from numpy.typing import NDArray

from airc.bridge.messages import DecisionSource, Quality
from airc.decision.result import Decision
from airc.decision.service import PartRequest
from airc.decision.worker import DecisionJob, DecisionWorker

CROP = np.full((8, 8, 3), 200, dtype=np.uint8)


class Echo:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.parts: list[PartRequest] = []
        self.closed = False

    async def decide(self, part: PartRequest, *, deadline_s: float | None = None) -> Decision:
        del deadline_s
        self.parts.append(part)
        if self.error is not None:
            raise self.error
        return Decision(part.part_id, Quality.SCRAP, 0.9, True, DecisionSource.AI, 5.0)

    async def aclose(self) -> None:
        self.closed = True


def _wait(worker: DecisionWorker, n: int = 1, timeout_s: float = 5.0) -> list[Decision]:
    out: list[Decision] = []
    end = time.monotonic() + timeout_s
    while len(out) < n and time.monotonic() < end:
        out += worker.poll()
        time.sleep(0.01)
    return out


def _job(
    part_id: int = 3, captured_at: float | None = None, crop: NDArray[np.uint8] = CROP
) -> DecisionJob:
    at = time.perf_counter() if captured_at is None else captured_at
    return DecisionJob(part_id, crop, "box", 0.8, captured_at=at)


def test_decides_in_the_worker_and_closes_the_service() -> None:
    echo = Echo()
    worker = DecisionWorker(lambda: echo, deadline_s=2.5)
    try:
        worker.submit(_job())
        [decision] = _wait(worker)
    finally:
        worker.close()
    assert decision.part_id == 3
    assert decision.source == DecisionSource.AI
    assert echo.parts[0].crop_png.startswith(b"\x89PNG")
    assert echo.closed


def test_no_time_left_falls_back_without_asking() -> None:
    echo = Echo()
    worker = DecisionWorker(lambda: echo, deadline_s=0.5)
    try:
        worker.submit(_job(captured_at=time.perf_counter() - 1.0))
        [decision] = _wait(worker)
    finally:
        worker.close()
    assert decision.source == DecisionSource.FALLBACK
    assert decision.reason == "no time left"
    assert echo.parts == []


def test_service_error_becomes_a_fallback() -> None:
    worker = DecisionWorker(lambda: Echo(RuntimeError("boom")), deadline_s=2.5)
    try:
        worker.submit(_job())
        worker.submit(_job(4, crop=np.zeros((0, 0, 3), dtype=np.uint8)))  # empty crop
        decisions = _wait(worker, 2)
    finally:
        worker.close()
    assert [d.source for d in decisions] == [DecisionSource.FALLBACK] * 2
    assert all(d.reason is not None and d.reason.startswith("error") for d in decisions)


def test_factory_error_is_raised_by_the_constructor() -> None:
    def broken() -> Echo:
        msg = "no recording"
        raise FileNotFoundError(msg)

    with pytest.raises(FileNotFoundError, match="no recording"):
        DecisionWorker(broken, deadline_s=2.5)
