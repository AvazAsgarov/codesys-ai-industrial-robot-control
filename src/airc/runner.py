"""The twin-bridge runner (``airc run``): one 20 ms cycle of PLC <-> twin exchange (spec §4.1).

Each cycle: read the PLC outputs -> step the twin with the joint setpoints, belt position and
vacuum command -> spawn parts due by belt travel -> answer a new capture request (Phase 2: from
ground truth) -> prepare joint feedback and sensors, which go out together with the next cycle's
read (one OPC UA round trip per cycle; the 20 ms extra age of the feedback is compensated by
``feedback_for_seq`` in the PLC). Cycles are paced on the monotonic clock;
a late cycle is counted as an overrun and the schedule restarts from now (no burst to catch up).
"""

import asyncio
import contextlib
import ctypes
import statistics
import sys
import time
from collections.abc import Callable, Coroutine, Generator
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from airc.bridge.client import BridgeClient, BridgeDisconnectedError
from airc.bridge.messages import PlcInputs, PlcOutputs, Six
from airc.bridge.oracle import GroundTruthOracle
from airc.twin.scenario import FaultEvent, FaultTimeline, Scenario, SpawnSchedule
from airc.twin.twin import Twin, TwinState

MM = 0.001
BLOCKED_DAMPING = 1e7  # N·m·s/rad: a blocked joint


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
    """Run this process above normal priority on Windows (the soft-PLC itself runs realtime)."""
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), ABOVE_NORMAL_PRIORITY_CLASS)


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

    @property
    def cycle_ms_mean(self) -> float:
        """Mean work time of a cycle (ms)."""
        return statistics.fmean(self.cycle_ms) if self.cycle_ms else 0.0

    @property
    def cycle_ms_p95(self) -> float:
        """95th percentile of the cycle work time (ms)."""
        if not self.cycle_ms:
            return 0.0
        ordered = sorted(self.cycle_ms)
        return ordered[max(0, int(len(ordered) * 0.95) - 1)]


def _six(values: np.ndarray) -> Six:
    v = [float(x) for x in values]
    return (v[0], v[1], v[2], v[3], v[4], v[5])


class Runner:
    """Runs the twin against the PLC through the bridge client."""

    def __init__(
        self,
        client: BridgeClient,
        twin: Twin,
        scenario: Scenario,
        period_s: float | None = None,
    ) -> None:
        """Create a runner.

        Args:
            client: Connected (or connectable) bridge client.
            twin: The digital twin.
            scenario: Part supply (and later faults).
            period_s: Cycle period; default from the twin configuration (20 ms).
        """
        self.client = client
        self.twin = twin
        self.scenario = scenario
        self.period_s = period_s if period_s is not None else twin.cfg.bridge_period_s
        self.schedule = SpawnSchedule(scenario)
        self.oracle = GroundTruthOracle(twin.geo.pe1_x)
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
        )

    async def cycle(self) -> None:
        """One exchange with the PLC (raises BridgeDisconnectedError if the link is lost)."""
        if self._pending is None:
            out = await self.client.read_outputs()
        else:  # last cycle's inputs go out together with this cycle's read: one round trip
            out, _ = await asyncio.gather(
                self.client.read_outputs(), self.client.write_inputs(self._pending)
            )
            self._pending = None
        state = self.twin.step(
            np.radians(np.array(out.joint_sp_deg)),
            out.belt_pos_mm * MM,
            out.belt_vel_mm_s * MM,
            out.vacuum_on,
        )
        for spec in self.schedule.due(out.belt_pos_mm):
            try:
                self.twin.spawn(spec)
                self._report.spawned += 1
            except RuntimeError:
                self._report.spawn_skipped += 1
        if out.capture.seq not in (0, self._last_capture):
            self._last_capture = out.capture.seq
            vision = self.oracle.on_capture(out.capture, self.twin.parts(), out.belt_pos_mm)
            await self.client.write_vision(vision)
            self._report.captures += 1
        self._pending = self._inputs(out, state)

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

        Returns:
            The run report.
        """
        await self.client.ensure_connected()  # connect first: the cycle gaps show steady state
        report = await self._loop(duration_s, stop)
        if self._pending is not None:  # flush the last cycle's inputs
            try:
                await self.client.write_inputs(self._pending)
            except BridgeDisconnectedError:
                report.reconnects += 1
            self._pending = None
        return report

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
                next_t += self.period_s
                await asyncio.sleep(max(0.0, next_t - time.perf_counter()))
                continue
            if self._last_start is not None:
                gap = (t0 - self._last_start) * 1000.0
                self._report.max_gap_ms = max(self._report.max_gap_ms, gap)
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
