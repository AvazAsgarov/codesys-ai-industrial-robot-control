"""The runner with the vision worker: captures answered from rendered frames, never blocking."""

import asyncio
import time
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from airc.bridge.client import BridgeClient
from airc.bridge.tags import TagMap
from airc.runner import Runner
from airc.twin.config import TwinConfig
from airc.twin.scenario import Scenario
from airc.twin.twin import PartSpec, Twin
from airc.vision.detector import Detection
from airc.vision.render import Frame
from airc.vision.service import VisionWorker
from tests.integration.fake_plc import FakePlc, free_port

pytestmark = pytest.mark.render

NO_SPAWN = Scenario.model_validate(
    {"name": "test", "seed": 1, "spawn": {"pitch_mm": 1e9, "jitter_mm": 0}}
)


class SlowOracle:
    """True masks after a delay (a slow detector)."""

    name = "slow-oracle"

    def __init__(self, twin: Twin, delay_s: float) -> None:
        self.twin = twin
        self.delay_s = delay_s
        self.bodies: NDArray[np.int32] | None = None

    def detect(self, rgb: NDArray[np.uint8]) -> list[Detection]:
        del rgb
        time.sleep(self.delay_s)
        assert self.bodies is not None
        out: list[Detection] = []
        for part in self.twin.parts():
            mask = self.bodies == self.twin.part_body_id(part.pid)
            if mask.sum() > 50:
                vs, us = np.nonzero(mask)
                box = (float(us.min()), float(vs.min()), float(us.max()), float(vs.max()))
                out.append(Detection("part", part.cls, 0.9, box, mask))
        return out


def _vision(twin: Twin, delay_s: float) -> VisionWorker:
    det = SlowOracle(twin, delay_s)

    def hook(frame: Frame) -> None:
        det.bodies = frame.bodies

    return VisionWorker(twin, lambda: det, frame_hook=hook)


def test_capture_answered_by_vision_without_blocking_the_cycle() -> None:
    async def scenario() -> dict[str, Any]:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        twin = Twin(cfg=TwinConfig.load(parts="catalogue"))
        vision = _vision(twin, delay_s=0.3)
        try:
            pid = twin.spawn(PartSpec(cls=2, y_mm=20.0, theta_deg=0.0, x_mm=twin.geo.pe1_x))
            await plc.set("capture.part_id", 5)
            await plc.set("capture.seq", 1)
            client = BridgeClient(plc.endpoint, TagMap.load())
            runner = Runner(client, twin, NO_SPAWN, vision=vision)
            report = await runner.run(duration_s=1.5)
            return {
                "seq_writes": plc.write_log.count("vision.seq"),
                "part_id": await plc.get("vision.part_id"),
                "cls": await plc.get("vision.cls"),
                "valid": await plc.get("vision.valid"),
                "x": await plc.get("vision.x_mm"),
                "truth_x": twin.part(pid).x_mm,
                "gap": report.max_gap_ms,
                "captures": report.captures,
            }
        finally:
            vision.close()
            await plc.stop()

    r = asyncio.run(scenario())
    assert r["seq_writes"] == 1
    assert (r["part_id"], r["cls"], r["valid"]) == (5, 2, True)
    assert r["x"] == pytest.approx(r["truth_x"], abs=10.0)
    assert r["captures"] == 1
    assert r["gap"] < 100.0  # the 300 ms detector never held up the 20 ms cycle
