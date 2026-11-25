"""DecisionService: deadline, rate limit, fallback, recording and replay, modes."""

import asyncio
import json
import time
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest

from airc.bridge.messages import DecisionSource, Quality
from airc.common.config import DecisionConfig
from airc.decision.ratelimit import TokenBucket
from airc.decision.recorder import Recorder, ReplaySource
from airc.decision.service import DecisionService, PartRequest, crop_to_png
from airc.decision.thx02 import Thx02Client
from tests.unit.decision.conftest import BASE_URL, PNG, FakeSleep, answer, transport

WINDOWS_TIMER_TICK_MS = 15.625  # default Windows clock resolution

API = DecisionConfig(mode="api", base_url=BASE_URL, deadline_s=2.5)


def _part(pid: int = 1, png: bytes = PNG) -> PartRequest:
    return PartRequest(part_id=pid, crop_png=png, detected_class="box", confidence=0.9)


def _service(handler, cfg: DecisionConfig = API, **kw) -> DecisionService:
    client = Thx02Client(cfg.base_url, transport=transport(handler), sleep=FakeSleep())
    return DecisionService(cfg, client=client, **kw)


def test_ai_decision_from_the_api(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answer("scrap", 0.77, 0.05))

    async def scenario():
        svc = _service(handler, recorder=Recorder(tmp_path / "r.jsonl", run_id="t"))
        try:
            return await svc.decide(_part(8))
        finally:
            await svc.aclose()

    d = asyncio.run(scenario())
    assert d.part_id == 8
    assert d.source is DecisionSource.AI
    assert d.quality is Quality.SCRAP
    assert d.quality_prob == pytest.approx(0.77)
    assert d.ident_reliable is False
    assert d.model == "THX-02"
    assert d.reason is None
    msg = d.to_msg(seq=3)
    assert (msg.seq, msg.part_id, int(msg.quality)) == (3, 8, 3)
    line = json.loads((tmp_path / "r.jsonl").read_text(encoding="utf-8"))
    assert line["part_id"] == 8
    assert line["error"] is None


def test_timeout_falls_back(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async def scenario():
        svc = _service(handler, recorder=Recorder(tmp_path / "r.jsonl", run_id="t"))
        return await svc.decide(_part())

    d = asyncio.run(scenario())
    assert d.source is DecisionSource.FALLBACK
    assert d.quality is Quality.OK
    assert d.reason == "timeout"
    line = json.loads((tmp_path / "r.jsonl").read_text(encoding="utf-8"))
    assert line["error"] == "timeout"
    assert line["response"] is None


def test_deadline_falls_back_without_waiting_for_the_api():
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5.0)
        return httpx.Response(200, json=answer())

    async def scenario():
        svc = _service(handler)
        t0 = time.perf_counter()
        d = await svc.decide(_part(), deadline_s=0.05)
        return d, time.perf_counter() - t0

    d, elapsed = asyncio.run(scenario())
    assert d.source is DecisionSource.FALLBACK
    assert d.reason == "deadline"
    assert elapsed < 1.0
    # the deadline was waited for; asyncio timers on Windows fire up to one clock tick
    # (about 15.6 ms) early, so a 50 ms deadline can measure 49 ms
    assert d.latency_ms >= 50.0 - WINDOWS_TIMER_TICK_MS


def test_config_deadline_is_the_default():
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5.0)
        return httpx.Response(200, json=answer())

    cfg = DecisionConfig(mode="api", base_url=BASE_URL, deadline_s=0.05)

    async def scenario():
        return await _service(handler, cfg).decide(_part())

    assert asyncio.run(scenario()).reason == "deadline"


def test_rate_limit_spaces_parts_two_decisions_each(fake_sleep: FakeSleep):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answer())

    bucket = TokenBucket(50.0, burst=2.0, clock=fake_sleep.clock, sleep=fake_sleep)
    starts: list[float] = []

    def spy(request: httpx.Request) -> httpx.Response:
        starts.append(fake_sleep.now)
        return handler(request)

    async def scenario():
        svc = _service(spy, limiter=bucket)
        for pid in range(3):
            await svc.decide(_part(pid))

    asyncio.run(scenario())
    assert starts == pytest.approx([0.0, 2.4, 4.8])


def test_429_falls_back_and_pauses_the_limiter(fake_sleep: FakeSleep):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"})

    bucket = TokenBucket(50.0, burst=2.0, clock=fake_sleep.clock, sleep=fake_sleep)

    async def scenario():
        svc = _service(handler, limiter=bucket)
        d = await svc.decide(_part())
        await bucket.acquire(2)
        return d

    d = asyncio.run(scenario())
    assert d.source is DecisionSource.FALLBACK
    assert d.reason == "rate_limited"
    assert fake_sleep.now >= 30.0


def test_bad_answer_falls_back_with_error_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "THX-02", "answers": {}})

    d = asyncio.run(_service(handler).decide(_part()))
    assert d.source is DecisionSource.FALLBACK
    assert d.reason is not None
    assert d.reason.startswith("error")


def test_mode_off_never_calls_the_api():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("mode off must not call the API")

    cfg = DecisionConfig(mode="off")
    d = asyncio.run(_service(handler, cfg).decide(_part(4)))
    assert d.part_id == 4
    assert d.source is DecisionSource.FALLBACK
    assert d.quality is Quality.OK
    assert d.reason == "mode off"


def test_replay_gives_identical_decisions(tmp_path: Path):
    path = tmp_path / "run.jsonl"
    script = {
        1: httpx.Response(200, json=answer("ok", 0.91, 0.97)),
        2: httpx.Response(200, json=answer("rework", 0.66, 0.4)),
        3: httpx.Response(200, json=answer("scrap", 0.88, 0.05)),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        pid = json.loads(json.loads(request.content)["state"])["detector_confidence"]
        key = round(pid * 10)
        if key == 4:
            raise httpx.ReadTimeout("slow", request=request)
        return script[key]

    def parts() -> list[PartRequest]:
        return [
            PartRequest(
                part_id=k, crop_png=PNG + bytes([k]), detected_class="can", confidence=k / 10
            )
            for k in (1, 2, 3, 4)
        ]

    async def live():
        svc = _service(handler, recorder=Recorder(path, run_id="seed-7", seed=7))
        return [await svc.decide(p) for p in parts()]

    async def replayed():
        cfg = DecisionConfig(mode="replay", replay_file=path)
        svc = DecisionService(cfg, replay=ReplaySource.load(path))
        return [await svc.decide(p) for p in parts()]

    first = asyncio.run(live())
    again = asyncio.run(replayed())

    def key(d):
        return (d.part_id, d.quality, d.quality_prob, d.ident_reliable, d.source, d.reason)

    assert [key(d) for d in again] == [key(d) for d in first]
    assert [d.source for d in first].count(DecisionSource.AI) == 3
    assert first[3].reason == "timeout"


def test_replay_miss_falls_back(tmp_path: Path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    cfg = DecisionConfig(mode="replay", replay_file=path)
    d = asyncio.run(DecisionService(cfg, replay=ReplaySource.load(path)).decide(_part(5)))
    assert d.source is DecisionSource.FALLBACK
    assert d.reason == "not recorded"


def test_from_config_builds_mode_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HALX_API_KEY", raising=False)
    cfg = DecisionConfig(mode="api", base_url=BASE_URL, record_dir=tmp_path / "rec")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answer())

    async def scenario():
        svc = DecisionService.from_config(cfg, run_id="run-a", seed=3, transport=transport(handler))
        try:
            return await svc.decide(_part())
        finally:
            await svc.aclose()

    assert asyncio.run(scenario()).source is DecisionSource.AI
    assert (tmp_path / "rec" / "run-a.jsonl").is_file()


def test_api_mode_without_client_is_rejected():
    with pytest.raises(ValueError, match="client"):
        DecisionService(API)


def test_crop_to_png_round_trips_rgb():
    rgb = np.zeros((4, 6, 3), dtype=np.uint8)
    rgb[..., 0] = 200  # red
    png = crop_to_png(rgb)
    assert png.startswith(b"\x89PNG")
    bgr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    assert bgr is not None
    assert bgr.shape == (4, 6, 3)
    assert int(bgr[0, 0, 2]) == 200


def test_crop_to_png_rejects_an_empty_crop():
    with pytest.raises(ValueError, match="empty"):
        crop_to_png(np.zeros((0, 0, 3), dtype=np.uint8))
