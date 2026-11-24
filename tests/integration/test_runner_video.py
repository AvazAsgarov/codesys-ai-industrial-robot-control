"""The runner with the video recorder: frames are rendered outside the bridge cycle."""

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any

import cv2
import pytest

from airc.bridge.client import BridgeClient
from airc.bridge.tags import TagMap
from airc.runner import Runner, RunReport, run_precise
from airc.twin.scenario import Scenario
from airc.twin.twin import Twin
from airc.video import VideoRecorder
from tests.integration.fake_plc import FakePlc, free_port

pytestmark = pytest.mark.render

NO_SPAWN = Scenario.model_validate(
    {"name": "test", "seed": 1, "spawn": {"pitch_mm": 1e9, "jitter_mm": 0}}
)
TIMING = {"cycles", "overruns", "cycle_ms", "max_gap_ms"}


def _outcome(report: RunReport) -> dict[str, Any]:
    return {k: v for k, v in asdict(report).items() if k not in TIMING}


def test_run_with_recorder_writes_a_video_and_keeps_the_report(tmp_path: Path) -> None:
    path = tmp_path / "run.mp4"

    async def scenario() -> tuple[RunReport, RunReport, VideoRecorder]:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            await plc.set("state", 6)  # Execute
            plain = Runner(BridgeClient(plc.endpoint, TagMap.load()), Twin(), NO_SPAWN)
            base = await plain.run(duration_s=1.0)
            twin = Twin()
            try:
                rec = VideoRecorder(twin, path, fps=10.0)
            except RuntimeError as exc:
                pytest.skip(f"no OpenGL context: {exc}")
            client = BridgeClient(plc.endpoint, TagMap.load())
            runner = Runner(client, twin, NO_SPAWN, recorder=rec)
            report = await runner.run(duration_s=1.0)  # closes the recorder
            return base, report, rec
        finally:
            await plc.stop()

    base, report, rec = run_precise(scenario())
    assert _outcome(report) == _outcome(base)
    assert report.cycles >= 40
    assert report.max_gap_ms < 400.0  # rendering never held up the 20 ms cycle
    assert path.is_file()
    assert rec.frames_written >= 8  # 10 frames per second for 1 s, a late one may be dropped
    cap = cv2.VideoCapture(str(path))
    frames = 0
    while cap.read()[0]:
        frames += 1
    cap.release()
    assert frames == rec.frames_written


def test_recorder_closed_when_the_run_is_cancelled(tmp_path: Path) -> None:
    path = tmp_path / "cancelled.mp4"

    async def scenario() -> VideoRecorder:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            twin = Twin()
            try:
                rec = VideoRecorder(twin, path, fps=10.0)
            except RuntimeError as exc:
                pytest.skip(f"no OpenGL context: {exc}")
            client = BridgeClient(plc.endpoint, TagMap.load())
            runner = Runner(client, twin, NO_SPAWN, recorder=rec)
            task = asyncio.create_task(runner.run())
            await asyncio.sleep(0.6)
            task.cancel()  # as Ctrl+C does
            with pytest.raises(asyncio.CancelledError):
                await task
            return rec
        finally:
            await plc.stop()

    rec = run_precise(scenario())
    assert rec.closed
    assert rec.frames_written >= 3
    cap = cv2.VideoCapture(str(path))
    assert cap.read()[0]  # a valid file
    cap.release()
