"""Async client for the hosted THX-02 decision API (ADR 0006, spec section 7).

One request per part carries two typed questions about the part crop: the quality disposition
(``choice`` over ok / rework / scrap) and whether the detector's identification is reliable
(``noul``, the probability of yes). Schema of ``POST /v1/decide`` as documented at
https://api.hal-x.ai/docs/thx-02/ and confirmed by a live call with a synthetic image
(``tests/fixtures/thx02``)::

    request  {"model": "thx-02", "state": str | object, "images": [data URI, ...],
              "questions": {name: {"type": "choice", "instructions": str,
                                   "criteria": {key: description}}
                            | {"type": "noul", "instructions": str}}}
    response {"model": "THX-02", "latency_ms": float, "usage": {...},
              "answers": {name: {"type": "choice", "choice": key, "confidence": float,
                                 "probabilities": {key: float}}
                          | {"type": "noul", "noul": float}}}
    errors   {"error": {"type": str, "message": str}}; 429 carries Retry-After.

The free tier counts every question as one decision (60 per minute per IP), so one part costs
:data:`DECISIONS_PER_PART` decisions.
"""

import asyncio
import base64
import email.utils
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self, cast

import httpx

from airc.bridge.messages import Quality

QUALITY_QUESTION = "quality"
IDENT_QUESTION = "ident_reliable"
DECISIONS_PER_PART = 2  # questions per request; the free tier counts each one
QUALITY_CRITERIA: dict[str, str] = {
    "ok": "Intact part without visible defects",
    "rework": "Small defect that can be repaired: dent, scratch, misprint or loose label",
    "scrap": "Severe damage, the part cannot be used: crushed, torn, broken or leaking",
}
QUALITY_BY_KEY: dict[str, Quality] = {
    "ok": Quality.OK,
    "rework": Quality.REWORK,
    "scrap": Quality.SCRAP,
}
MAX_BODY_BYTES = 8_000_000  # documented limit: "Keep the whole body under 8 MB"
DECIDE_PATH = "/v1/decide"
HTTP_TOO_MANY_REQUESTS = 429
DEFAULT_RETRY_AFTER_S = 1.0  # when a 429 comes without a usable Retry-After

Sleep = Callable[[float], Awaitable[None]]
Json = dict[str, Any]


class Thx02Error(Exception):
    """A THX-02 call failed; the caller falls back to the rule baseline."""


class Thx02TimeoutError(Thx02Error):
    """The request did not complete within the per-call timeout."""


class Thx02RateLimitedError(Thx02Error):
    """The API answered 429 and waiting would take too long (or retries ran out)."""

    def __init__(self, retry_after_s: float) -> None:
        """Remember how long the API asked to wait.

        Args:
            retry_after_s: The ``Retry-After`` of the last 429, in seconds.
        """
        super().__init__(f"rate limited, retry after {retry_after_s:g} s")
        self.retry_after_s = retry_after_s


class Thx02ResponseError(Thx02Error):
    """The API answered with an error status or with a body that does not fit the schema."""


@dataclass(frozen=True)
class PartDecision:
    """THX-02's answer about one part."""

    quality: Quality
    quality_prob: float  # probability of the chosen quality option
    probabilities: dict[str, float]  # every quality option
    ident_prob: float  # probability that the identification is reliable (noul = yes)
    ident_reliable: bool
    model: str
    latency_ms: float  # round trip seen by the client
    model_latency_ms: float | None  # time in the model, as reported by the API
    raw: Json = field(repr=False)


def build_request(
    crop_png: bytes, detected_class: str, confidence: float, *, model: str = "thx-02"
) -> Json:
    """Build the ``/v1/decide`` body for one part.

    Args:
        crop_png: PNG-encoded crop of the part.
        detected_class: The detector's class name (e.g. ``box``).
        confidence: The detector's confidence, 0..1.
        model: Model id; without ``thx-02`` the API answers with THX-01.

    Returns:
        The JSON body as a dict.
    """
    state = json.dumps(
        {"detected_class": detected_class, "detector_confidence": round(confidence, 4)}
    )
    return {
        "model": model,
        "state": state,
        "images": ["data:image/png;base64," + base64.b64encode(crop_png).decode("ascii")],
        "questions": {
            QUALITY_QUESTION: {
                "type": "choice",
                "instructions": "What is the quality disposition of the part in the image?",
                "criteria": dict(QUALITY_CRITERIA),
            },
            IDENT_QUESTION: {
                "type": "noul",
                "instructions": (
                    f"Does the image show one whole {detected_class}, as the detector says?"
                ),
            },
        },
    }


def encode_body(body: Mapping[str, Any]) -> bytes:
    """Serialise a request body canonically (the bytes sent, and the bytes hashed)."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _probability(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"{what} is not a number: {value!r}"
        raise Thx02ResponseError(msg)
    return float(value)


def parse_response(
    raw: Json, *, latency_ms: float, unreliable_no_prob: float = 0.8
) -> PartDecision:
    """Turn a ``/v1/decide`` response into a :class:`PartDecision`.

    Args:
        raw: The decoded JSON response.
        latency_ms: Round-trip latency of the call.
        unreliable_no_prob: The identification counts as unreliable when the probability of
            "no" reaches this value (spec 7.2: "no" with high probability -> quarantine).

    Returns:
        The decision.

    Raises:
        Thx02ResponseError: If the response does not have both answers in the documented shape.
    """
    answers = raw.get("answers")
    if not isinstance(answers, dict):
        msg = "response has no answers"
        raise Thx02ResponseError(msg)
    answers = cast("dict[str, Any]", answers)
    quality = answers.get(QUALITY_QUESTION)
    ident = answers.get(IDENT_QUESTION)
    if not isinstance(quality, dict) or not isinstance(ident, dict):
        msg = f"response lacks the {QUALITY_QUESTION!r} or {IDENT_QUESTION!r} answer"
        raise Thx02ResponseError(msg)
    quality = cast("dict[str, Any]", quality)
    ident = cast("dict[str, Any]", ident)
    choice = quality.get("choice")
    probs_raw = quality.get("probabilities")
    if choice not in QUALITY_BY_KEY or not isinstance(probs_raw, dict):
        msg = f"unexpected quality answer: {quality!r}"
        raise Thx02ResponseError(msg)
    probs = {
        str(k): _probability(v, f"probability of {k}")
        for k, v in cast("dict[str, Any]", probs_raw).items()
    }
    if choice not in probs:
        msg = f"quality choice {choice!r} has no probability"
        raise Thx02ResponseError(msg)
    p_yes = _probability(ident.get("noul"), "ident noul")
    model_latency = raw.get("latency_ms")
    return PartDecision(
        quality=QUALITY_BY_KEY[cast("str", choice)],
        quality_prob=probs[cast("str", choice)],
        probabilities=probs,
        ident_prob=p_yes,
        ident_reliable=(1.0 - p_yes) < unreliable_no_prob,
        model=str(raw.get("model", "")),
        latency_ms=latency_ms,
        model_latency_ms=(float(model_latency) if isinstance(model_latency, int | float) else None),
        raw=raw,
    )


def retry_after_seconds(value: str | None, now: datetime | None = None) -> float:
    """Parse a ``Retry-After`` header (delta seconds or HTTP date) into seconds (>= 0)."""
    if not value:
        return DEFAULT_RETRY_AFTER_S
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_S
    current = now if now is not None else datetime.now(UTC)
    return max(0.0, (when - current).total_seconds())


def _error_message(response: httpx.Response) -> str:
    try:
        body: object = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        err = cast("dict[str, Any]", body).get("error")
        if isinstance(err, dict):
            err_dict = cast("dict[str, Any]", err)
            return str(err_dict.get("message", err_dict))
    return response.text[:200]


class Thx02Client:
    """Talks to ``POST /v1/decide``; one instance holds one HTTP connection pool."""

    def __init__(  # noqa: PLR0913 - keyword configuration of one client
        self,
        base_url: str,
        *,
        model: str = "thx-02",
        timeout_s: float = 2.0,
        api_key: str | None = None,
        unreliable_no_prob: float = 0.8,
        max_retry_wait_s: float = 1.0,
        max_429_retries: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        """Create a client.

        Args:
            base_url: API root, e.g. ``https://api.hal-x.ai`` (from ``config/cell.yaml``).
            model: Model id sent in every request.
            timeout_s: Per-call timeout (connect, write, read each).
            api_key: Optional HAL-X key (bearer token); without it the free tier applies.
            unreliable_no_prob: See :func:`parse_response`.
            max_retry_wait_s: A 429 whose ``Retry-After`` is longer raises at once.
            max_429_retries: How many 429s are waited out before giving up.
            transport: HTTP transport (tests pass ``httpx.MockTransport``).
            sleep: Awaitable sleep (tests pass a fake clock).
        """
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._http = httpx.AsyncClient(
            base_url=base_url, timeout=timeout_s, headers=headers, transport=transport
        )
        self.model = model
        self._unreliable_no_prob = unreliable_no_prob
        self._max_retry_wait_s = max_retry_wait_s
        self._max_429_retries = max_429_retries
        self._sleep = sleep

    async def __aenter__(self) -> Self:
        """Use the client as an async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the connection pool."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the connection pool."""
        await self._http.aclose()

    def build_request(self, crop_png: bytes, detected_class: str, confidence: float) -> Json:
        """:func:`build_request` with this client's model id."""
        return build_request(crop_png, detected_class, confidence, model=self.model)

    def parse(self, raw: Json, latency_ms: float) -> PartDecision:
        """:func:`parse_response` with this client's reliability threshold."""
        return parse_response(
            raw, latency_ms=latency_ms, unreliable_no_prob=self._unreliable_no_prob
        )

    async def post(self, body: Mapping[str, Any]) -> tuple[Json, float]:
        """Send one decide request, waiting out short 429s.

        Args:
            body: The request body (see :func:`build_request`).

        Returns:
            The decoded response and the round-trip latency in ms (including 429 waits).

        Raises:
            ValueError: If the body is over the API's 8 MB limit.
            Thx02TimeoutError: If a call times out.
            Thx02RateLimitedError: If a 429 asks for a longer wait or retries ran out.
            Thx02ResponseError: On any other error status or a non-JSON body.
            Thx02Error: On transport errors.
        """
        content = encode_body(body)
        if len(content) >= MAX_BODY_BYTES:
            msg = f"request body is {len(content)} bytes; the API accepts under 8 MB"
            raise ValueError(msg)
        t0 = time.perf_counter()
        retries = 0
        while True:
            try:
                response = await self._http.post(DECIDE_PATH, content=content)
            except httpx.TimeoutException as exc:
                raise Thx02TimeoutError(f"THX-02 call timed out: {exc!r}") from exc
            except httpx.HTTPError as exc:
                raise Thx02Error(f"THX-02 call failed: {exc!r}") from exc
            if response.status_code == HTTP_TOO_MANY_REQUESTS:
                wait = retry_after_seconds(response.headers.get("Retry-After"))
                if wait > self._max_retry_wait_s or retries >= self._max_429_retries:
                    raise Thx02RateLimitedError(wait)
                retries += 1
                await self._sleep(wait)
                continue
            if response.is_error:
                msg = f"THX-02 answered {response.status_code}: {_error_message(response)}"
                raise Thx02ResponseError(msg)
            try:
                raw: object = response.json()
            except ValueError as exc:
                raise Thx02ResponseError("THX-02 answered with a non-JSON body") from exc
            if not isinstance(raw, dict):
                msg = "THX-02 answered with a non-object body"
                raise Thx02ResponseError(msg)
            return cast("Json", raw), (time.perf_counter() - t0) * 1000.0

    async def decide_part(
        self, crop_png: bytes, detected_class: str, confidence: float
    ) -> PartDecision:
        """Ask THX-02 about one part (one request, both questions).

        Args:
            crop_png: PNG-encoded crop of the part.
            detected_class: The detector's class name.
            confidence: The detector's confidence, 0..1.

        Returns:
            Quality, its probability, identification reliability, raw response and latency.

        Raises:
            Thx02Error: See :meth:`post` (and :class:`Thx02ResponseError` for a bad answer).
            ValueError: If the request is too large.
        """
        raw, latency_ms = await self.post(self.build_request(crop_png, detected_class, confidence))
        return self.parse(raw, latency_ms)
