"""Shared helpers for the decision-layer tests (no network: httpx.MockTransport only)."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "thx02"
BASE_URL = "https://thx.test"
PNG = b"\x89PNG\r\n\x1a\n-synthetic-crop-"


def fixture_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def answer(quality: str = "ok", p_quality: float = 0.9, p_ident: float = 0.95) -> dict[str, Any]:
    rest = (1.0 - p_quality) / 2
    probs = {k: (p_quality if k == quality else rest) for k in ("ok", "rework", "scrap")}
    return {
        "model": "THX-02",
        "answers": {
            "quality": {
                "type": "choice",
                "choice": quality,
                "confidence": 0.8,
                "probabilities": probs,
            },
            "ident_reliable": {"type": "noul", "noul": p_ident},
        },
        "usage": {"input_tokens": 300, "output_tokens": 0, "thoughts": 0},
        "latency_ms": 120.0,
    }


class FakeSleep:
    """Records requested sleeps and advances a fake clock instead of waiting."""

    def __init__(self) -> None:
        self.now = 0.0
        self.calls: list[float] = []

    def clock(self) -> float:
        return self.now

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_sleep() -> FakeSleep:
    return FakeSleep()


def transport(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)
