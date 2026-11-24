"""Decision worker: runs the decision service in its own thread and event loop.

The runner submits a part when its vision result arrives and polls finished decisions each
bridge cycle; neither call waits. PNG encoding, the rate-limit wait, the HTTP call and the
recording all happen in the worker, so a slow or stuck THX-02 never delays the 20 ms bridge
cycle. The worker never raises for a part: any error gives the rule fallback with its reason.
"""

import asyncio
import contextlib
import logging
import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from airc.decision.fallback import fallback_decision
from airc.decision.result import Decision
from airc.decision.service import PartRequest, crop_to_png

CLOSE_TIMEOUT_S = 5.0

_log = logging.getLogger(__name__)


class DecisionBackend(Protocol):
    """What the worker needs of a decision service (:class:`DecisionService` or a test fake)."""

    async def decide(self, part: PartRequest, *, deadline_s: float | None = None) -> Decision:
        """Decide one part within ``deadline_s``."""
        ...

    async def aclose(self) -> None:
        """Release resources (HTTP connections)."""
        ...


@dataclass(frozen=True)
class DecisionJob:
    """One part to decide, as the runner knows it when the vision result arrives."""

    part_id: int
    crop: NDArray[np.uint8]  # RGB crop of the part (VisionResult.crop)
    detected_class: str
    confidence: float
    captured_at: float  # time.perf_counter() of the capture: the PLC's deadline runs from it


class DecisionWorker:
    """A thread with its own event loop that owns the decision service."""

    def __init__(self, factory: Callable[[], DecisionBackend], *, deadline_s: float) -> None:
        """Start the worker and build the service in it.

        Args:
            factory: Creates the service inside the worker thread (so its HTTP client, rate
                limiter and recorder belong to the worker's event loop).
            deadline_s: The PLC's decision deadline, counted from the capture; what is left of
                it when the job starts is the service's budget.

        Raises:
            Exception: Whatever ``factory`` raised (e.g. a missing replay file).
        """
        self.deadline_s = deadline_s
        self._factory = factory
        self._loop = asyncio.new_event_loop()
        self._done: queue.Queue[Decision] = queue.Queue()
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._service: DecisionBackend | None = None
        self._futures: set[Future[None]] = set()
        self._thread = threading.Thread(target=self._run, name="decision", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error is not None:
            self._thread.join(timeout=CLOSE_TIMEOUT_S)
            raise self._error

    def submit(self, job: DecisionJob) -> None:
        """Queue a part (returns at once)."""
        future = asyncio.run_coroutine_threadsafe(self._decide(job), self._loop)
        self._futures.add(future)
        future.add_done_callback(self._futures.discard)

    def poll(self) -> list[Decision]:
        """Decisions finished since the last poll, in completion order (never blocks)."""
        out: list[Decision] = []
        with contextlib.suppress(queue.Empty):
            while True:
                out.append(self._done.get_nowait())
        return out

    def close(self) -> None:
        """Cancel pending parts, close the service and stop the thread."""
        if self._loop.is_closed() or not self._thread.is_alive():
            return
        shutdown = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        with contextlib.suppress(Exception):
            shutdown.result(timeout=CLOSE_TIMEOUT_S)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=CLOSE_TIMEOUT_S)

    # --- worker thread ---------------------------------------------------------------------------
    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._service = self._factory()
        except BaseException as exc:  # handed to the constructor, which raises it
            self._error = exc
            self._ready.set()
            self._loop.close()
            return
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _decide(self, job: DecisionJob) -> None:
        assert self._service is not None
        t0 = time.perf_counter()
        budget_s = self.deadline_s - (t0 - job.captured_at)
        try:
            if budget_s <= 0.0:
                decision = fallback_decision(job.part_id, reason="no time left")
            else:
                part = PartRequest(
                    job.part_id, crop_to_png(job.crop), job.detected_class, job.confidence
                )
                decision = await self._service.decide(part, deadline_s=budget_s)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the cell must keep running: the PLC falls back on its own
            _log.warning("part %d: decision failed: %r", job.part_id, exc)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            decision = fallback_decision(
                job.part_id, reason=f"error: {exc!r}", latency_ms=latency_ms
            )
        self._done.put(decision)

    async def _shutdown(self) -> None:
        current = asyncio.current_task()
        pending = [t for t in asyncio.all_tasks(self._loop) if t is not current]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if self._service is not None:
            await self._service.aclose()
