"""The twin-bridge runner (``airc run``): one 20 ms cycle of PLC <-> twin exchange (spec §4.1).

Each cycle: read the PLC outputs -> step the twin with the joint setpoints, belt position and
vacuum command -> spawn parts due by belt travel -> answer a new capture request (Phase 2: from
ground truth) -> prepare joint feedback and sensors, which go out together with the next cycle's
read (one OPC UA round trip per cycle; the 20 ms extra age of the feedback is compensated by
``feedback_for_seq`` in the PLC). Cycles are paced on the monotonic clock;
a late cycle is counted as an overrun and the schedule restarts from now (no burst to catch up).

With a decision worker (Phase 4), each valid vision result with a crop is also sent to THX-02
in the worker's thread; an AI decision that comes back for a part still before the pick
window is written to the PLC (at most one per cycle). Fallbacks are never written: the PLC's
own deadline rule (alarm ``DecisionFallback``) decides those parts (ADR 0006).
"""

import asyncio
import contextlib
import ctypes
import logging
import os
import statistics
import sys
import time
from collections import deque
from collections.abc import Callable, Coroutine, Generator
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np

from airc.bridge.client import BridgeClient, BridgeDisconnectedError
from airc.bridge.messages import DecisionSource, PackMLState, PlcInputs, PlcOutputs, Six
from airc.bridge.oracle import GroundTruthOracle
from airc.decision.result import Decision
from airc.decision.worker import DecisionJob, DecisionWorker
from airc.plc.runtime import disable_timer_throttling
from airc.twin.scenario import FaultEvent, FaultTimeline, Scenario, SpawnSchedule
from airc.twin.twin import MAX_STEP_S, Twin, TwinState
from airc.vision.service import CaptureJob, VisionResult

if TYPE_CHECKING:
    from airc.video import VideoRecorder  # OpenCV only when recording

MM = 0.001
BLOCKED_DAMPING = 1e7  # N·m·s/rad: a blocked joint
GAP_LOG_MS = 200.0  # log a cycle longer than this (the PLC's bridge watchdog is 500 ms)
RECORDER_CYCLES = 50  # flight recorder: cycles kept, dumped when the cell leaves Execute
_STOPPED_BY_FAULT = {PackMLState.ABORTING, PackMLState.ABORTED, PackMLState.STOPPING}

_log = logging.getLogger(__name__)


_BaseLoop: type[asyncio.AbstractEventLoop] = (
    asyncio.ProactorEventLoop if sys.platform == "win32" else asyncio.SelectorEventLoop
)


class PerfCounterLoop(_BaseLoop):  # type: ignore[misc, valid-type]
    """Event loop whose clock is ``time.perf_counter``.

    asyncio's default clock is ``time.monotonic``, which ticks every 15.6 ms on Windows: timers
    then wake up to that late, whatever the system timer resolution is.
    """

    def time(self) -> float:
        """The loop's clock."""
        return time.perf_counter()


@contextlib.contextmanager
def fine_timer() -> Generator[None]:
    """Use 1 ms timer resolution on Windows while running (default: 15.6 ms).

    Without it every ``asyncio.sleep`` of a 20 ms cycle is rounded to 15.6 or 31.2 ms.
    """
    if sys.platform != "win32":
        yield
        return
    winmm = ctypes.WinDLL("winmm")
    winmm.timeBeginPeriod(1)
    try:
        yield
    finally:
        winmm.timeEndPeriod(1)


ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000


def raise_priority() -> None:
    """Run this process above normal priority on Windows, exempt from timer throttling.

    Windows 11 slows timers of processes it considers background work (power throttling);
    the bridge cycle must keep its 20 ms pace, as the soft-PLC's task does (ADR 0008).
    """
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), ABOVE_NORMAL_PRIORITY_CLASS)
        disable_timer_throttling(os.getpid())


class VisionSource(Protocol):
    """Answers captures off the bridge loop (:class:`~airc.vision.service.VisionWorker`)."""

    def submit(self, job: CaptureJob) -> None:
        """Queue a capture (returns at once)."""
        ...

    def poll(self) -> list[VisionResult]:
        """Results finished since the last poll (never blocks)."""
        ...


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, int(len(ordered) * q) - 1)]


def run_precise[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine on a :class:`PerfCounterLoop` with 1 ms system timer resolution."""
    with fine_timer(), asyncio.Runner(loop_factory=PerfCounterLoop) as runner:
        return runner.run(coro)


@dataclass
class RunReport:
    """Outcome of a run (counts and cycle timing)."""

    cycles: int = 0
    overruns: int = 0
    reconnects: int = 0
    spawned: int = 0
    spawn_skipped: int = 0
    captures: int = 0
    bin_counts: tuple[int, ...] = ()
    wrong_bin: int = 0
    missed: int = 0  # ran off the end of the belt without being picked
    lost: int = 0  # on the floor anywhere else (e.g. missed a bin on release)
    cycle_ms: list[float] = field(default_factory=list[float])
    max_gap_ms: float = 0.0  # longest time between two cycle starts
    faults: int = 0
    vision: list[VisionResult] = field(default_factory=list[VisionResult])  # answers, in order
    decision_requests: int = 0  # parts sent to the decision worker
    decisions: list[Decision] = field(default_factory=list[Decision])  # all answers, AI or not
    decisions_written: int = 0  # AI decisions written to the PLC
    decisions_dropped: int = 0  # AI decisions too late (part at the pick window) or unknown part

    @property
    def cycle_ms_mean(self) -> float:
        """Mean work time of a cycle (ms)."""
        return statistics.fmean(self.cycle_ms) if self.cycle_ms else 0.0

    @property
    def cycle_ms_p95(self) -> float:
        """95th percentile of the cycle work time (ms)."""
        return _percentile(self.cycle_ms, 0.95)

    @property
    def decision_fallbacks(self) -> int:
        """Decisions that came back as the rule fallback (never written to the PLC)."""
        return sum(d.source != DecisionSource.AI for d in self.decisions)

    @property
    def decision_latency_ms_p50(self) -> float:
        """Median decision latency (ms), fallbacks included."""
        return _percentile([d.latency_ms for d in self.decisions], 0.50)

    @property
    def decision_latency_ms_p95(self) -> float:
        """95th percentile of the decision latency (ms), fallbacks included."""
        return _percentile([d.latency_ms for d in self.decisions], 0.95)


def _state_name(state: int) -> str:
    try:
        return PackMLState(state).name
    except ValueError:
        return f"STATE {state}"


def _six(values: np.ndarray) -> Six:
    v = [float(x) for x in values]
    return (v[0], v[1], v[2], v[3], v[4], v[5])


class Runner:
    """Runs the twin against the PLC through the bridge client."""

    def __init__(  # noqa: PLR0913 - the runner's collaborators
        self,
        client: BridgeClient,
        twin: Twin,
        scenario: Scenario,
        *,
        period_s: float | None = None,
        vision: VisionSource | None = None,
        decision: DecisionWorker | None = None,
        recorder: "VideoRecorder | None" = None,
    ) -> None:
        """Create a runner.

        Args:
            client: Connected (or connectable) bridge client.
            twin: The digital twin.
            scenario: Part supply (and later faults).
            period_s: Cycle period; default from the twin configuration (20 ms).
            vision: Answers captures from camera frames (in its own thread); default: the
                ground-truth stand-in (Phase 2).
            decision: Asks THX-02 about each part vision saw (in its own thread); needs
                ``vision`` (the oracle has no image). ``None``: the PLC's fallback rule decides.
            recorder: Renders a video of the run (in its own thread); closed when
                :meth:`run` ends.
        """
        self.client = client
        self.twin = twin
        self.scenario = scenario
        self.period_s = period_s if period_s is not None else twin.cfg.bridge_period_s
        self.schedule = SpawnSchedule(scenario)
        self.oracle = GroundTruthOracle(twin.geo.pe1_x)
        self.vision = vision
        self.recorder = recorder
        self._unwritten: list[VisionResult] = []  # vision answers not yet written to the PLC
        self.decision = decision
        self.pick_start_x = twin.geo.pe2_x  # belt frame: a decision must arrive before this
        self._captured_at: dict[int, float] = {}  # PLC part id -> perf_counter at the capture
        self._awaiting: dict[int, tuple[float, float]] = {}  # part id -> (x, belt) at capture
        self._decided: deque[Decision] = deque()  # decisions not yet handled
        self._decision_seq = 0
        self.faults = FaultTimeline(scenario)
        self.door_closed = True
        self.estop_ok = True
        self.bridge_lost = False
        self._forced_full: set[int] = set()
        self._saved_damping: dict[int, float] = {}
        self._t0: float | None = None
        self.after_cycle: Callable[[], None] | None = None  # e.g. a viewer sync
        self._heartbeat = False
        self._feedback_seq = 0
        self._last_capture = 0
        self._pending: PlcInputs | None = None
        self._recorder: deque[str] = deque(maxlen=RECORDER_CYCLES)
        self._last_state = 0
        self._dt_s: float | None = None  # real duration of the last cycle (None: nominal)
        self._last_start: float | None = None
        self._report = RunReport()

    def _inputs(self, out: PlcOutputs, state: TwinState) -> PlcInputs:
        self._heartbeat = not self._heartbeat
        self._feedback_seq += 1
        full = tuple(f or i in self._forced_full for i, f in enumerate(state.bin_full))
        return PlcInputs(
            heartbeat=self._heartbeat,
            twin_active=True,
            joint_fb_deg=_six(np.degrees(state.joint_pos_rad)),
            joint_torque_nm=_six(state.joint_torque_nm),
            feedback_seq=self._feedback_seq,
            feedback_for_seq=out.setpoint_seq,
            pe1=state.pe1,
            pe2=state.pe2,
            vacuum_ok=state.vacuum_ok,
            bin_full=(full[0], full[1], full[2], full[3], full[4], full[5]),
            door_closed=self.door_closed,
            estop_ok=self.estop_ok,
            decision_active=self.decision is not None,
        )

    async def cycle(self) -> None:
        """One exchange with the PLC (raises BridgeDisconnectedError if the link is lost)."""
        t0 = time.perf_counter()
        if self._pending is None:
            out = await self.client.read_outputs()
        else:  # last cycle's inputs go out together with this cycle's read: one round trip
            out, _ = await asyncio.gather(
                self.client.read_outputs(), self.client.write_inputs(self._pending)
            )
            self._pending = None
        t1 = time.perf_counter()
        state = self.twin.step(
            np.radians(np.array(out.joint_sp_deg)),
            out.belt_pos_mm * MM,
            out.belt_vel_mm_s * MM,
            out.vacuum_on,
            dt_s=self._dt_s if self._dt_s is not None else self.period_s,
        )
        self._record(out, state)
        for spec in self.schedule.due(out.belt_pos_mm):
            try:
                self.twin.spawn(spec)
                self._report.spawned += 1
            except RuntimeError:
                self._report.spawn_skipped += 1
        if self.recorder is not None:  # a state copy every 1/fps s; rendered in its thread
            self.recorder.capture(self.twin, _state_name(out.state), sum(state.bin_counts))
        t2 = time.perf_counter()
        if self.vision is not None:
            if out.capture.seq not in (0, self._last_capture):
                self.vision.submit(CaptureJob.snapshot(self.twin, out.capture, out.belt_pos_mm))
                self._last_capture = out.capture.seq
                self._captured_at[out.capture.part_id] = t0
                self._report.captures += 1
            for result in self.vision.poll():
                self._unwritten.append(result)
                self._request_decision(result)
            while self._unwritten:  # a failed write stays here and is re-sent after reconnect
                await self.client.write_vision(self._unwritten[0].msg)
                self._report.vision.append(self._unwritten.pop(0))
            if self.decision is not None:  # after the vision: the PLC needs that first
                await self._handle_decisions(out.belt_pos_mm)
        elif out.capture.seq not in (0, self._last_capture):
            vision = self.oracle.on_capture(out.capture, self.twin.parts(), out.belt_pos_mm)
            await self.client.write_vision(vision)
            self._last_capture = out.capture.seq  # only once written: a lost write is re-sent
            self._report.captures += 1
        self._pending = self._inputs(out, state)
        t3 = time.perf_counter()
        if (t3 - t0) * 1000.0 > GAP_LOG_MS:
            _log.warning(
                "cycle took %.0f ms (exchange %.0f, twin %.0f, vision %.0f ms)",
                (t3 - t0) * 1000.0,
                (t1 - t0) * 1000.0,
                (t2 - t1) * 1000.0,
                (t3 - t2) * 1000.0,
            )

    def _request_decision(self, result: VisionResult) -> None:
        """Send a part vision saw (with its crop) to the decision worker (returns at once)."""
        msg = result.msg
        captured_at = self._captured_at.pop(msg.part_id, None)
        if self.decision is None or not msg.valid or result.crop.size == 0 or result.job is None:
            return
        classes = self.twin.cfg.parts.classes
        name = classes[msg.cls].name if 0 <= msg.cls < len(classes) else str(msg.cls)
        self._awaiting[msg.part_id] = (msg.x_mm, result.job.capture.belt_pos_mm)
        at = captured_at if captured_at is not None else time.perf_counter()
        self.decision.submit(DecisionJob(msg.part_id, result.crop, name, msg.confidence, at))
        self._report.decision_requests += 1

    async def _handle_decisions(self, belt_pos_mm: float) -> None:
        """Write the next AI decision still in time; log and count the others (never waits)."""
        assert self.decision is not None
        self._decided.extend(self.decision.poll())
        while self._decided:
            decision = self._decided[0]
            where = self._awaiting.get(decision.part_id)
            write = False
            if decision.source != DecisionSource.AI:  # the PLC's deadline rule decides the part
                _log.info("part %d: no AI decision (%s)", decision.part_id, decision.reason)
            elif where is None:
                _log.warning("part %d: decision for an unknown part dropped", decision.part_id)
                self._report.decisions_dropped += 1
            elif (x := where[0] + belt_pos_mm - where[1]) >= self.pick_start_x:
                _log.warning(
                    "part %d: decision after %.0f ms dropped: part at %.0f mm, pick window %.0f",
                    decision.part_id,
                    decision.latency_ms,
                    x,
                    self.pick_start_x,
                )
                self._report.decisions_dropped += 1
            else:  # a failed write raises here: the decision stays first and is re-sent
                self._decision_seq += 1
                await self.client.write_decision(decision.to_msg(self._decision_seq))
                self._report.decisions_written += 1
                write = True
            self._decided.popleft()
            self._awaiting.pop(decision.part_id, None)
            self._report.decisions.append(decision)
            if write:
                break  # one write per cycle: the PLC sees every sequence number

    def _record(self, out: PlcOutputs, state: TwinState) -> None:
        """Flight recorder: keep the last cycles; dump them when the cell leaves Execute."""
        err = np.abs(np.degrees(state.joint_pos_rad) - np.array(out.joint_sp_deg))
        joint = int(np.argmax(err)) + 1
        contacts = ",".join(self.twin.held_contacts()) or "-"
        dt_ms = (self._dt_s if self._dt_s is not None else self.period_s) * 1000.0
        self._recorder.append(
            f"dt {dt_ms:5.1f} ms seq {out.setpoint_seq} max error {err.max():6.2f} deg (J{joint}) "
            f"vacuum {int(out.vacuum_on)}/{int(state.vacuum_ok)} held-part contacts {contacts}"
        )
        if self._last_state == PackMLState.EXECUTE and out.state in _STOPPED_BY_FAULT:
            _log.warning(
                "flight recorder: last %d cycles before %s\n%s",
                len(self._recorder),
                PackMLState(out.state).name,
                "\n".join(self._recorder),
            )
        self._last_state = out.state

    def _apply(self, event: FaultEvent) -> None:
        fault, on = event.fault, event.start
        target = fault.target if fault.target is not None else 0
        match fault.kind:
            case "estop":
                self.estop_ok = not on
            case "door_open":
                self.door_closed = not on
            case "lose_bridge":
                self.bridge_lost = on
            case "drop_part":
                if on:
                    self.twin.drop_part(block_grip=True)
                else:
                    self.twin.allow_grip()
            case "block_bin":
                if on:
                    self._forced_full.add(target)
                else:
                    self._forced_full.discard(target)
            case "block_joint":
                if on:
                    self._saved_damping[target] = self.twin.joint_damping(target)
                    self.twin.set_joint_damping(target, BLOCKED_DAMPING)
                else:
                    self.twin.set_joint_damping(target, self._saved_damping.pop(target))
        self._report.faults += int(on)

    def _finish(self) -> RunReport:
        report = self._report
        state = self.twin.state()
        report.bin_counts = state.bin_counts
        belt_top = self.twin.geo.belt_surface_z
        for part in self.twin.parts():
            if part.in_bin is not None and part.in_bin != part.cls:
                report.wrong_bin += 1
            elif part.in_bin is None and part.z_mm < belt_top - 100.0:
                if part.x_mm > self.twin.cfg.belt.length_mm:
                    report.missed += 1
                else:
                    report.lost += 1
        return report

    async def run(
        self, duration_s: float | None = None, stop: asyncio.Event | None = None
    ) -> RunReport:
        """Run cycles until ``duration_s`` passes or ``stop`` is set.

        The video recorder, if any, is closed when the run ends (also on an error or when the
        run is cancelled, e.g. by Ctrl+C), so its file is complete.

        Returns:
            The run report.
        """
        try:
            await self.client.ensure_connected()  # connect first: the cycle gaps show steady state
            report = await self._loop(duration_s, stop)
            if self._pending is not None:  # flush the last cycle's inputs
                # no decision service after the run: the PLC decides by its rule again
                last = replace(self._pending, decision_active=False)
                try:
                    await self.client.write_inputs(last)
                except BridgeDisconnectedError:
                    report.reconnects += 1
                self._pending = None
            return report
        finally:
            if self.recorder is not None:
                self.recorder.close()

    async def _loop(self, duration_s: float | None, stop: asyncio.Event | None) -> RunReport:
        # perf_counter, not loop.time(): time.monotonic ticks every 15.6 ms on Windows
        start = time.perf_counter()
        next_t = start
        while stop is None or not stop.is_set():
            if duration_s is not None and time.perf_counter() - start >= duration_s:
                break
            t0 = time.perf_counter()
            if self._t0 is None:
                self._t0 = t0
            for event in self.faults.events(t0 - self._t0):
                self._apply(event)
            if self.bridge_lost:  # fault: no exchange with the PLC, the twin stands still
                self._last_start = None
                self._dt_s = None
                next_t += self.period_s
                await asyncio.sleep(max(0.0, next_t - time.perf_counter()))
                continue
            if self._last_start is not None:
                gap = (t0 - self._last_start) * 1000.0
                self._report.max_gap_ms = max(self._report.max_gap_ms, gap)
                self._dt_s = min(max(gap / 1000.0, self.period_s), MAX_STEP_S)
            self._last_start = t0
            try:
                await self.client.ensure_connected()
                await self.cycle()
                if self.after_cycle is not None:
                    self.after_cycle()
                self._report.cycles += 1
                self._report.cycle_ms.append((time.perf_counter() - t0) * 1000.0)
            except BridgeDisconnectedError:
                self._report.reconnects += 1
            next_t += self.period_s
            if next_t < time.perf_counter():
                self._report.overruns += 1
                next_t = time.perf_counter()
            else:
                await asyncio.sleep(next_t - time.perf_counter())
        return self._finish()
