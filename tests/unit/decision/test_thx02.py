"""THX-02 hosted-API client: request shape, response parsing, timeouts, 429 handling."""

import asyncio
import base64
import json

import httpx
import pytest

from airc.bridge.messages import Quality
from airc.decision.thx02 import (
    IDENT_QUESTION,
    QUALITY_QUESTION,
    Thx02Client,
    Thx02RateLimitedError,
    Thx02ResponseError,
    Thx02TimeoutError,
    build_request,
    parse_response,
)
from tests.unit.decision.conftest import BASE_URL, PNG, FakeSleep, answer, fixture_json, transport


def _client(handler, fake_sleep: FakeSleep | None = None, **kw) -> Thx02Client:
    return Thx02Client(
        BASE_URL,
        transport=transport(handler),
        sleep=fake_sleep if fake_sleep is not None else FakeSleep(),
        **kw,
    )


def test_build_request_carries_both_questions_and_the_image():
    body = build_request(PNG, "box", 0.87, model="thx-02")
    assert body["model"] == "thx-02"
    assert set(body["questions"]) == {QUALITY_QUESTION, IDENT_QUESTION}
    quality = body["questions"][QUALITY_QUESTION]
    assert quality["type"] == "choice"
    assert list(quality["criteria"]) == ["ok", "rework", "scrap"]
    assert body["questions"][IDENT_QUESTION]["type"] == "noul"
    assert "box" in body["questions"][IDENT_QUESTION]["instructions"]
    assert body["images"] == ["data:image/png;base64," + base64.b64encode(PNG).decode()]
    state = json.loads(body["state"])
    assert state == {"detected_class": "box", "detector_confidence": 0.87}


def test_decide_part_posts_one_request_to_v1_decide():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answer("rework", 0.7, 0.9))

    async def scenario():
        async with _client(handler) as client:
            return await client.decide_part(PNG, "jar", 0.8)

    decision = asyncio.run(scenario())
    assert len(seen) == 1
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == f"{BASE_URL}/v1/decide"
    assert req.headers["content-type"] == "application/json"
    body = json.loads(req.content)
    assert set(body["questions"]) == {QUALITY_QUESTION, IDENT_QUESTION}
    assert len(body["images"]) == 1
    assert decision.quality is Quality.REWORK
    assert decision.quality_prob == pytest.approx(0.7)
    assert decision.ident_reliable is True
    assert decision.latency_ms >= 0.0
    assert decision.raw["model"] == "THX-02"


def test_api_key_is_sent_as_bearer_token_only_when_given():
    headers: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        headers.append(request.headers)
        return httpx.Response(200, json=answer())

    async def scenario():
        async with _client(handler) as anon:
            await anon.decide_part(PNG, "box", 0.9)
        async with _client(handler, api_key="sk-test") as keyed:
            await keyed.decide_part(PNG, "box", 0.9)

    asyncio.run(scenario())
    assert "authorization" not in headers[0]
    assert headers[1]["authorization"] == "Bearer sk-test"


def test_parse_saved_fixture():
    raw = fixture_json("decide_response.json")
    decision = parse_response(raw, latency_ms=812.0)
    assert decision.quality is Quality.OK
    assert decision.quality_prob == pytest.approx(raw["answers"]["quality"]["probabilities"]["ok"])
    assert set(decision.probabilities) == {"ok", "rework", "scrap"}
    assert decision.ident_prob == pytest.approx(raw["answers"]["ident_reliable"]["noul"])
    assert decision.ident_reliable is True
    assert decision.model == "THX-02"
    assert decision.latency_ms == 812.0
    assert decision.model_latency_ms == pytest.approx(raw["latency_ms"])


def test_fixture_request_matches_what_the_client_builds():
    saved = fixture_json("decide_request.json")
    built = build_request(PNG, "box", 0.91, model="thx-02")
    assert saved["questions"] == built["questions"]
    assert saved["model"] == built["model"]
    assert json.loads(saved["state"]) == json.loads(built["state"])


def test_ident_unreliable_when_no_is_likely():
    decision = parse_response(answer(p_ident=0.1), latency_ms=1.0, unreliable_no_prob=0.8)
    assert decision.ident_reliable is False
    unsure = parse_response(answer(p_ident=0.4), latency_ms=1.0, unreliable_no_prob=0.8)
    assert unsure.ident_reliable is True


@pytest.mark.parametrize(
    "raw",
    [
        {"answers": {}},
        {"answers": {"quality": {"type": "choice", "choice": "maybe", "probabilities": {}}}},
        {"model": "THX-02"},
    ],
)
def test_malformed_response_raises(raw):
    with pytest.raises(Thx02ResponseError):
        parse_response(raw, latency_ms=1.0)


def test_timeout_raises_typed_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async def scenario():
        async with _client(handler, timeout_s=0.5) as client:
            await client.decide_part(PNG, "box", 0.9)

    with pytest.raises(Thx02TimeoutError):
        asyncio.run(scenario())


def test_error_envelope_raises_response_error_with_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"type": "invalid", "message": "no state"}})

    async def scenario():
        async with _client(handler) as client:
            await client.decide_part(PNG, "box", 0.9)

    with pytest.raises(Thx02ResponseError, match="no state"):
        asyncio.run(scenario())


def test_429_honours_retry_after_then_succeeds(fake_sleep: FakeSleep):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": {}})
        return httpx.Response(200, json=answer())

    async def scenario():
        async with _client(handler, fake_sleep, max_retry_wait_s=5.0) as client:
            return await client.decide_part(PNG, "box", 0.9)

    decision = asyncio.run(scenario())
    assert calls == 2
    assert fake_sleep.calls == [2.0]
    assert decision.quality is Quality.OK


def test_429_with_long_retry_after_raises_with_the_wait(fake_sleep: FakeSleep):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"})

    async def scenario():
        async with _client(handler, fake_sleep, max_retry_wait_s=5.0) as client:
            await client.decide_part(PNG, "box", 0.9)

    with pytest.raises(Thx02RateLimitedError) as info:
        asyncio.run(scenario())
    assert info.value.retry_after_s == 30.0
    assert fake_sleep.calls == []


def test_429_retries_are_bounded(fake_sleep: FakeSleep):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "1"})

    async def scenario():
        async with _client(handler, fake_sleep, max_retry_wait_s=5.0, max_429_retries=2) as c:
            await c.decide_part(PNG, "box", 0.9)

    with pytest.raises(Thx02RateLimitedError):
        asyncio.run(scenario())
    assert fake_sleep.calls == [1.0, 1.0]


def test_body_over_8_mb_is_rejected_before_sending():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not be sent")

    async def scenario():
        async with _client(handler) as client:
            await client.decide_part(b"x" * 7_000_000, "box", 0.9)

    with pytest.raises(ValueError, match="8 MB"):
        asyncio.run(scenario())
