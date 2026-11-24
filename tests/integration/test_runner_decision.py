"""The runner with the decision worker, against the in-process fake PLC (no network, no render).

A fake vision source answers each capture at once with a crop; a fake decision service stands
in for THX-02. Only AI decisions for a part still before the pick point reach the PLC.
"""

import asyncio
import time
from dataclasses import dataclass, field

import numpy as np

from airc.bridge.client import BridgeClient
from airc.bridge.messages import DecisionSource, Quality, VisionMsg
from airc.bridge.tags import TagMap
from airc.decision.result import Decision
from airc.decision.service import PartRequest
from airc.decision.worker import DecisionWorker
from airc.runner import Runner, RunReport, run_precise
from airc.twin.scenario import Scenario
from airc.twin.twin import Twin
from airc.vision.service import CaptureJob, VisionResult
from tests.integration.fake_plc import FakePlc, free_port

NO_SPAWN = Scenario.model_validate(
    {"name": "test", "seed": 1, "spawn": {"pitch_mm": 1e9, "jitter_mm": 0}}
)
PART_ID = 7
CLS = 1


@dataclass
class FakeVision:
    """Answers every capture at once: part seen at ``x_mm`` (belt frame), with a crop."""

    x_mm: float
    jobs: list[CaptureJob] = field(default_factory=list[CaptureJob])
    _done: list[VisionResult] = field(default_factory=list[VisionResult])

    def submit(self, job: CaptureJob) -> None:
        self.jobs.append(job)
        msg = VisionMsg(len(self.jobs), job.capture.part_id, True, CLS, 0.9, self.x_mm, 5.0, 0.0)
        crop = np.full((16, 24, 3), 128, dtype=np.uint8)
        self._done.append(VisionResult(msg=msg, latency_ms=1.0, detections=1, crop=crop, job=job))

    def poll(self) -> list[VisionResult]:
        out, self._done = self._done, []
        return out


@dataclass
class FakeDecisionService:
    """Answers after ``delay_s``; ``blocking`` sleeps the thread instead of awaiting."""

    delay_s: float = 0.0
    source: DecisionSource = DecisionSource.AI
    blocking: bool = False
    part_id_offset: int = 0
    requests: list[tuple[PartRequest, float | None]] = field(
        default_factory=list[tuple[PartRequest, float | None]]
    )
    closed: bool = False

    async def decide(self, part: PartRequest, *, deadline_s: float | None = None) -> Decision:
        self.requests.append((part, deadline_s))
        if self.blocking:
            time.sleep(self.delay_s)
        else:
            await asyncio.sleep(self.delay_s)
        fallback = self.source == DecisionSource.FALLBACK
        return Decision(
            part_id=part.part_id + self.part_id_offset,
            quality=Quality.OK if fallback else Quality.REWORK,
            quality_prob=0.0 if fallback else 0.8,
            ident_reliable=fallback,
            source=self.source,
            latency_ms=self.delay_s * 1000.0,
            reason="deadline" if fallback else None,
        )

    async def aclose(self) -> None:
        self.closed = True


async def _capture(plc: FakePlc, belt_pos_mm: float = 0.0) -> None:
    await plc.set("capture.part_id", PART_ID)
    await plc.set("capture.belt_pos_mm", belt_pos_mm)
    await plc.set("capture.seq", 1)


async def _run(
    plc: FakePlc,
    service: FakeDecisionService,
    duration_s: float,
    *,
    belt_after: tuple[float, float] | None = None,
) -> RunReport:
    """Run the runner; ``belt_after`` = (seconds, belt position) moves the belt meanwhile."""
    twin = Twin()
    worker = DecisionWorker(lambda: service, deadline_s=2.5)
    try:
        client = BridgeClient(plc.endpoint, TagMap.load())
        runner = Runner(client, twin, NO_SPAWN, vision=FakeVision(twin.geo.pe1_x), decision=worker)
        task = asyncio.create_task(runner.run(duration_s=duration_s))
        if belt_after is not None:
            await asyncio.sleep(belt_after[0])
            await plc.set("belt_pos_mm", belt_after[1])
        return await task
    finally:
        worker.close()


def test_decision_written_for_the_captured_part() -> None:
    service = FakeDecisionService()

    async def scenario() -> tuple[RunReport, dict[str, object], list[str]]:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            await _capture(plc)
            report = await _run(plc, service, 0.5)
            got = {
                name: await plc.get(f"decision.{name}")
                for name in ("part_id", "quality", "quality_prob", "ident_reliable", "seq")
            }
            return report, got, list(plc.write_log)
        finally:
            await plc.stop()

    report, got, log = asyncio.run(scenario())
    part, deadline = service.requests[0]
    assert part.part_id == PART_ID
    assert part.crop_png.startswith(b"\x89PNG")
    assert part.detected_class == Twin().cfg.parts.classes[CLS].name
    assert part.confidence == 0.9
    assert deadline is not None
    assert 0.0 < deadline <= 2.5
    assert log.count("decision.seq") == 1
    assert log.index("vision.seq") < log.index("decision.seq")  # the PLC needs the vision first
    assert got["part_id"] == PART_ID
    assert got["quality"] == int(Quality.REWORK)
    assert got["ident_reliable"] is False
    assert got["seq"] == 1
    assert report.decisions_written == 1
    assert report.decision_fallbacks == 0
    assert len(report.decisions) == 1
    assert service.closed


def test_fallback_is_not_written() -> None:
    service = FakeDecisionService(source=DecisionSource.FALLBACK)

    async def scenario() -> tuple[RunReport, list[str]]:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            await _capture(plc)
            report = await _run(plc, service, 0.5)
            return report, list(plc.write_log)
        finally:
            await plc.stop()

    report, log = asyncio.run(scenario())
    assert len(service.requests) == 1
    assert "vision.seq" in log
    assert "decision.seq" not in log  # the PLC's own fallback (DecisionFallback) handles it
    assert report.decision_fallbacks == 1
    assert report.decisions_written == 0


def test_slow_decision_never_delays_the_cycle() -> None:
    service = FakeDecisionService(delay_s=0.6, blocking=True)

    async def scenario() -> tuple[RunReport, list[str]]:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            await _capture(plc)
            report = await _run(plc, service, 1.2)
            return report, list(plc.write_log)
        finally:
            await plc.stop()

    report, log = run_precise(scenario())
    assert log.count("decision.seq") == 1  # it arrived after 600 ms and was still written
    assert report.max_gap_ms < 100.0  # the 600 ms decision never held up the 20 ms cycle
    assert report.cycles >= 45
    assert report.decision_latency_ms_p50 >= 600.0


def test_decision_for_a_part_past_the_pick_point_is_dropped() -> None:
    service = FakeDecisionService(delay_s=0.4)

    async def scenario() -> tuple[RunReport, list[str]]:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            await _capture(plc)
            # the part reaches the pick window (PE2) while THX-02 is still thinking
            report = await _run(plc, service, 0.8, belt_after=(0.15, 900.0))
            return report, list(plc.write_log)
        finally:
            await plc.stop()

    report, log = asyncio.run(scenario())
    assert len(service.requests) == 1  # requested while the part was before the pick point
    assert "decision.seq" not in log
    assert report.decisions_dropped == 1
    assert report.decisions_written == 0


def test_decision_for_another_part_is_dropped() -> None:
    service = FakeDecisionService(part_id_offset=1)

    async def scenario() -> tuple[RunReport, list[str]]:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            await _capture(plc)
            report = await _run(plc, service, 0.5)
            return report, list(plc.write_log)
        finally:
            await plc.stop()

    report, log = asyncio.run(scenario())
    assert "decision.seq" not in log
    assert report.decisions_dropped == 1


def test_decision_active_written_true_with_a_decision_service() -> None:
    async def scenario() -> list[object]:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            await _run(plc, FakeDecisionService(), 0.3)
            return [v for name, v in plc.write_values if name == "decision_active"]
        finally:
            await plc.stop()

    flags = asyncio.run(scenario())
    assert len(flags) >= 10  # every cycle, with the other inputs
    assert all(flags[:-1])  # the PLC waits for THX-02 (up to tDecisionDeadline)
    assert flags[-1] is False  # on shutdown: the PLC decides by its rule again


def test_decision_active_false_without_a_decision_service() -> None:
    async def scenario() -> list[object]:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            client = BridgeClient(plc.endpoint, TagMap.load())
            twin = Twin()
            await Runner(client, twin, NO_SPAWN, vision=FakeVision(twin.geo.pe1_x)).run(0.3)
            return [v for name, v in plc.write_values if name == "decision_active"]
        finally:
            await plc.stop()

    flags = asyncio.run(scenario())
    assert len(flags) >= 10
    assert not any(flags)  # the PLC decides each part by its rule as soon as vision has it
