"""JSONL recording of THX-02 exchanges and the replay source (spec 7.4)."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from airc.decision.recorder import Recorder, ReplaySource, payload_sha256
from airc.decision.thx02 import build_request, encode_body
from tests.unit.decision.conftest import PNG, answer


def test_payload_hash_is_sha256_of_the_bytes_sent():
    body = build_request(PNG, "box", 0.9)
    assert payload_sha256(body) == hashlib.sha256(encode_body(body)).hexdigest()


def test_record_writes_one_json_line_per_exchange_without_image_bytes(tmp_path: Path):
    path = tmp_path / "rec" / "run.jsonl"
    body = build_request(PNG, "box", 0.9)

    async def scenario():
        rec = Recorder(path, run_id="run-1", seed=42)
        await rec.record(3, body, response=answer(), latency_ms=512.5, model="thx-02")
        await rec.record(4, body, error="deadline", latency_ms=2500.0, model="thx-02")

    asyncio.run(scenario())
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["run_id"] == "run-1"
    assert first["seed"] == 42
    assert first["part_id"] == 3
    assert first["model"] == "thx-02"
    assert first["response_model"] == "THX-02"
    assert first["latency_ms"] == 512.5
    assert first["payload_sha256"] == payload_sha256(body)
    assert first["timestamp"].endswith("Z")
    assert first["response"] == answer()
    assert first["error"] is None
    image_ref = first["request"]["images"][0]
    assert image_ref == "sha256:" + hashlib.sha256(PNG).hexdigest()
    assert first["request"]["questions"] == body["questions"]
    second = json.loads(lines[1])
    assert second["error"] == "deadline"
    assert second["response"] is None


def test_replay_round_trip_by_payload_hash_then_part_id(tmp_path: Path):
    path = tmp_path / "run.jsonl"
    body_a = build_request(PNG, "box", 0.9)
    body_b = build_request(PNG + b"b", "can", 0.7)

    async def scenario():
        rec = Recorder(path, run_id="r", seed=1)
        await rec.record(1, body_a, response=answer("scrap", 0.8), latency_ms=10.0)
        await rec.record(2, body_b, error="rate_limited", latency_ms=5.0)

    asyncio.run(scenario())
    replay = ReplaySource.load(path)
    assert len(replay) == 2
    hit = replay.lookup(payload_sha256(body_a), part_id=99)
    assert hit is not None
    assert hit.response == answer("scrap", 0.8)
    assert hit.part_id == 1
    by_part = replay.lookup("0" * 64, part_id=2)
    assert by_part is not None
    assert by_part.error == "rate_limited"
    assert replay.lookup("0" * 64, part_id=7) is None


def test_replay_rejects_a_broken_line(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"part_id": 1}\nnot json\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad\.jsonl:1"):
        ReplaySource.load(path)
