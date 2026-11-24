"""The twin-bridge runner against the in-process fake PLC."""

import asyncio
import logging
import time
from itertools import pairwise

import pytest

from airc.bridge.client import BridgeClient, BridgeDisconnectedError
from airc.bridge.messages import VisionMsg
from airc.bridge.tags import TagMap
from airc.runner import Runner, run_precise
from airc.twin.scenario import Scenario
from airc.twin.twin import PartSpec, Twin
from tests.integration.fake_plc import FakePlc, free_port

NO_SPAWN = Scenario.model_validate(
    {"name": "test", "seed": 1, "spawn": {"pitch_mm": 1e9, "jitter_mm": 0}}
)


async def _runner(plc: FakePlc, twin: Twin) -> Runner:
    client = BridgeClient(plc.endpoint, TagMap.load())
    await client.connect()
    return Runner(client, twin, NO_SPAWN)


def test_heartbeat_toggles_every_cycle() -> None:
    async def scenario() -> None:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            runner = await _runner(plc, Twin())
            report = await runner.run(duration_s=0.4)
            beats = [v for name, v in plc.write_values if name == "heartbeat"]
            assert report.cycles >= 10
            assert len(beats) == report.cycles
            assert all(a != b for a, b in pairwise(beats))
            assert await plc.get("twin_active") is True
            assert await plc.get("feedback_seq") == report.cycles
        finally:
            await plc.stop()

    asyncio.run(scenario())


def test_feedback_answers_the_setpoint_sample() -> None:
    async def scenario() -> None:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            await plc.set("setpoint_seq", 4711)
            await plc.set("joint_sp_deg", [0.0, -30.0, 60.0, 0.0, 60.0, 0.0])
            runner = await _runner(plc, Twin())
            await runner.run(duration_s=0.2)
            assert await plc.get("feedback_for_seq") == 4711
        finally:
            await plc.stop()

    asyncio.run(scenario())


def test_capture_answered_with_ground_truth_once() -> None:
    async def scenario() -> None:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            twin = Twin()
            pe1 = twin.geo.pe1_x
            pid = twin.spawn(PartSpec(cls=2, y_mm=25.0, theta_deg=12.0, x_mm=pe1 - 35.0))
            await plc.set("capture.part_id", 7)
            await plc.set("capture.belt_pos_mm", 0.0)
            await plc.set("capture.seq", 1)
            runner = await _runner(plc, twin)
            await runner.run(duration_s=0.3)
            assert plc.write_log.count("vision.seq") == 1
            assert await plc.get("vision.part_id") == 7
            assert await plc.get("vision.cls") == 2
            assert await plc.get("vision.valid") is True
            truth = twin.part(pid)
            assert await plc.get("vision.x_mm") == pytest.approx(truth.x_mm, abs=1.0)
            assert await plc.get("vision.y_mm") == pytest.approx(25.0, abs=1.0)
            assert await plc.get("vision.theta_deg") == pytest.approx(12.0, abs=0.5)
        finally:
            await plc.stop()

    asyncio.run(scenario())


def test_cycle_overrun_counted() -> None:
    async def scenario() -> None:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            twin = Twin()
            real_step = twin.step

            def slow_step(*args: object, **kwargs: object) -> object:
                time.sleep(0.05)  # longer than the 20 ms cycle
                return real_step(*args, **kwargs)  # type: ignore[arg-type]

            twin.step = slow_step  # type: ignore[method-assign]
            runner = await _runner(plc, twin)
            report = await runner.run(duration_s=0.5)
            assert report.overruns >= report.cycles - 1
            assert report.overruns > 0
        finally:
            await plc.stop()

    asyncio.run(scenario())


def test_paces_at_the_cycle_period() -> None:
    async def scenario() -> None:  # on the runner's perf_counter event loop, as `airc run` does
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            runner = await _runner(plc, Twin())
            report = await runner.run(duration_s=2.0)
            # 20 ms cycles; the fake server shares this event loop and the machine may be busy,
            # so throughput is checked loosely - what the PLC needs is no long gap (watchdog 500 ms)
            assert 80 <= report.cycles <= 101
            assert report.max_gap_ms < 150.0
        finally:
            await plc.stop()

    run_precise(scenario())


def test_faults_drive_plc_inputs() -> None:
    async def scenario() -> None:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            faults = Scenario.model_validate(
                {
                    "name": "faults",
                    "seed": 1,
                    "spawn": {"pitch_mm": 1e9},
                    "faults": [
                        {"at_s": 0.1, "kind": "estop", "duration_s": 0.3},
                        {"at_s": 0.1, "kind": "block_bin", "duration_s": 0.3, "target": 2},
                    ],
                }
            )
            client = BridgeClient(plc.endpoint, TagMap.load())
            runner = Runner(client, Twin(), faults)
            await runner.run(duration_s=0.25)
            assert await plc.get("estop_ok") is False
            assert (await plc.get("bin_full"))[2] is True
            await runner.run(duration_s=0.4)
            assert await plc.get("estop_ok") is True
            assert (await plc.get("bin_full"))[2] is False
        finally:
            await plc.stop()

    asyncio.run(scenario())


def test_capture_answered_again_after_a_failed_write() -> None:
    async def scenario() -> None:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            await plc.set("capture.part_id", 9)
            await plc.set("capture.seq", 1)
            runner = await _runner(plc, Twin())
            real_write = runner.client.write_vision
            failures = [1]

            async def flaky_write(msg: VisionMsg) -> None:
                if failures:
                    failures.pop()
                    await runner.client.close()
                    raise BridgeDisconnectedError("link lost during the vision write")
                await real_write(msg)

            runner.client.write_vision = flaky_write  # type: ignore[method-assign]
            report = await runner.run(duration_s=0.4)
            assert report.reconnects >= 1
            assert plc.write_log.count("vision.seq") == 1
            assert await plc.get("vision.part_id") == 9
        finally:
            await plc.stop()

    asyncio.run(scenario())


def test_long_cycle_gap_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    async def scenario() -> None:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            twin = Twin()
            real_step = twin.step
            slow = [1]

            def stall_once(*args: object, **kwargs: object) -> object:
                if slow:
                    slow.pop()
                    time.sleep(0.25)
                return real_step(*args, **kwargs)  # type: ignore[arg-type]

            twin.step = stall_once  # type: ignore[method-assign]
            runner = await _runner(plc, twin)
            with caplog.at_level(logging.WARNING, logger="airc.runner"):
                await runner.run(duration_s=0.5)
            assert any("cycle took" in r.message and "twin" in r.message for r in caplog.records)
        finally:
            await plc.stop()

    asyncio.run(scenario())


def test_twin_steps_by_the_real_cycle_time() -> None:
    async def scenario() -> None:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            twin = Twin()
            real_step = twin.step
            dts: list[float] = []

            def slow_step(*args: object, **kwargs: object) -> object:
                dts.append(float(kwargs.get("dt_s", 0.0)))  # type: ignore[arg-type]
                time.sleep(0.03)  # every cycle takes longer than 20 ms
                return real_step(*args, **kwargs)  # type: ignore[arg-type]

            twin.step = slow_step  # type: ignore[method-assign]
            runner = await _runner(plc, twin)
            await runner.run(duration_s=0.5)
            assert dts[0] == pytest.approx(0.02)  # first cycle: the nominal period
            assert min(dts[2:]) >= 0.03  # then the time that really passed
        finally:
            await plc.stop()

    asyncio.run(scenario())


def test_flight_recorder_dumped_when_the_cell_aborts(caplog: pytest.LogCaptureFixture) -> None:
    async def scenario() -> None:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            await plc.set("state", 6)  # Execute
            runner = await _runner(plc, Twin())
            task = asyncio.create_task(runner.run(duration_s=0.6))
            await asyncio.sleep(0.3)
            await plc.set("state", 8)  # Aborting
            with caplog.at_level(logging.WARNING, logger="airc.runner"):
                await task
            dumps = [r.message for r in caplog.records if "flight recorder" in r.message]
            assert len(dumps) == 1  # once per transition
            assert "ABORTING" in dumps[0]
            assert "max error" in dumps[0]
        finally:
            await plc.stop()

    asyncio.run(scenario())
