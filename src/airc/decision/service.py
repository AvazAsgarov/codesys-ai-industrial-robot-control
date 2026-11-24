"""Decision service: one THX-02 decision per part, always within the deadline (spec 7).

``decide`` never raises for API trouble: a missed deadline, a timeout, a 429, an error status or
an answer that does not fit the schema all give the rule fallback (source ``FALLBACK``) with the
reason. Modes (``config/cell.yaml``, ``decision.mode``):

- ``api``: ask the hosted API under the client-side rate limit and record every exchange;
- ``replay``: answer from a recording, so a run can be repeated without calling the API;
- ``off``: always the rule fallback (the "rule-based only" ablation arm).
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import cv2
import httpx
import numpy as np
from numpy.typing import NDArray

from airc.bridge.messages import DecisionSource
from airc.common.config import DecisionConfig
from airc.decision.fallback import fallback_decision
from airc.decision.ratelimit import TokenBucket
from airc.decision.recorder import Recorder, ReplaySource, payload_sha256
from airc.decision.result import Decision
from airc.decision.thx02 import (
    DECISIONS_PER_PART,
    PartDecision,
    Thx02Client,
    Thx02Error,
    Thx02RateLimitedError,
    Thx02TimeoutError,
    build_request,
    parse_response,
)

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PartRequest:
    """What the decision layer gets about one part (from the vision result)."""

    part_id: int
    crop_png: bytes
    detected_class: str
    confidence: float


def crop_to_png(rgb: NDArray[np.uint8]) -> bytes:
    """PNG-encode an RGB crop (``VisionResult.crop``); run it off the event loop.

    Raises:
        ValueError: If the crop is empty (no part was chosen) or cannot be encoded.
    """
    if rgb.size == 0:
        msg = "empty crop: no part to decide on"
        raise ValueError(msg)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if not ok:
        msg = "PNG encoding of the crop failed"
        raise ValueError(msg)
    return buf.tobytes()


def _ms_since(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def _ai(part_id: int, answer: PartDecision, latency_ms: float) -> Decision:
    return Decision(
        part_id=part_id,
        quality=answer.quality,
        quality_prob=answer.quality_prob,
        ident_reliable=answer.ident_reliable,
        source=DecisionSource.AI,
        latency_ms=latency_ms,
        model=answer.model,
    )


class DecisionService:
    """Turns parts into decisions in mode ``api``, ``replay`` or ``off``."""

    def __init__(
        self,
        cfg: DecisionConfig,
        *,
        client: Thx02Client | None = None,
        replay: ReplaySource | None = None,
        recorder: Recorder | None = None,
        limiter: TokenBucket | None = None,
    ) -> None:
        """Assemble a service from its parts (see :meth:`from_config` for the usual way).

        Args:
            cfg: The ``decision`` block of the cell configuration.
            client: THX-02 client, required in mode ``api``.
            replay: Recording to answer from, required in mode ``replay``.
            recorder: Where to record exchanges in mode ``api`` (``None``: not recorded).
            limiter: Client-side rate limit in mode ``api`` (``None``: unlimited).

        Raises:
            ValueError: If the mode's required part is missing.
        """
        if cfg.mode == "api" and client is None:
            msg = "mode api needs a THX-02 client"
            raise ValueError(msg)
        if cfg.mode == "replay" and replay is None:
            msg = "mode replay needs a replay source"
            raise ValueError(msg)
        self.cfg = cfg
        self._client = client
        self._replay = replay
        self._recorder = recorder
        self._limiter = limiter

    @classmethod
    def from_config(
        cls,
        cfg: DecisionConfig,
        *,
        run_id: str,
        seed: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "DecisionService":
        """Build the service a mode needs. Call it before the bridge loop starts.

        Args:
            cfg: The ``decision`` block of the cell configuration.
            run_id: Names the recording (``<record_dir>/<run_id>.jsonl``).
            seed: Scenario seed, stored with every record.
            transport: HTTP transport override (tests).

        Returns:
            The service.
        """
        if cfg.mode == "off":
            return cls(cfg)
        if cfg.mode == "replay":
            assert cfg.replay_file is not None  # checked by DecisionConfig
            return cls(cfg, replay=ReplaySource.load(cfg.replay_file))
        client = Thx02Client(
            cfg.base_url,
            model=cfg.model,
            timeout_s=cfg.request_timeout_s,
            api_key=os.environ.get(cfg.api_key_env) or None,
            unreliable_no_prob=cfg.unreliable_no_prob,
            max_retry_wait_s=cfg.max_retry_wait_s,
            max_429_retries=cfg.max_429_retries,
            transport=transport,
        )
        recorder = (
            Recorder(cfg.record_dir / f"{run_id}.jsonl", run_id=run_id, seed=seed)
            if cfg.record_dir is not None
            else None
        )
        limiter = TokenBucket(cfg.rate_limit_per_min, burst=cfg.burst)
        return cls(cfg, client=client, recorder=recorder, limiter=limiter)

    async def aclose(self) -> None:
        """Release the HTTP connections."""
        if self._client is not None:
            await self._client.aclose()

    async def decide(self, part: PartRequest, *, deadline_s: float | None = None) -> Decision:
        """Decide quality and identification reliability for one part.

        Args:
            part: The part.
            deadline_s: Time budget for this part (default ``cfg.deadline_s``), including the
                wait for the rate limit.

        Returns:
            An AI decision, or the rule fallback with the reason.
        """
        t0 = time.perf_counter()
        if self.cfg.mode == "off":
            return fallback_decision(part.part_id, reason="mode off")
        body = build_request(
            part.crop_png, part.detected_class, part.confidence, model=self.cfg.model
        )
        if self.cfg.mode == "replay":
            return self._from_replay(part, body, t0)
        return await self._from_api(part, body, t0, deadline_s or self.cfg.deadline_s)

    def _from_replay(self, part: PartRequest, body: dict[str, Any], t0: float) -> Decision:
        assert self._replay is not None
        hit = self._replay.lookup(payload_sha256(body), part.part_id)
        if hit is None:
            return self._fallback(part, "not recorded", t0)
        if hit.error is not None or hit.response is None:
            return self._fallback(part, hit.error or "no response", t0)
        try:
            answer = parse_response(
                hit.response,
                latency_ms=hit.latency_ms,
                unreliable_no_prob=self.cfg.unreliable_no_prob,
            )
        except Thx02Error as exc:
            return self._fallback(part, f"error: {exc}", t0)
        return _ai(part.part_id, answer, hit.latency_ms)

    async def _from_api(
        self, part: PartRequest, body: dict[str, Any], t0: float, deadline_s: float
    ) -> Decision:
        assert self._client is not None
        raw: dict[str, Any] | None = None
        api_ms = 0.0
        reason: str | None = None
        answer: PartDecision | None = None
        try:
            async with asyncio.timeout(deadline_s):
                if self._limiter is not None:
                    await self._limiter.acquire(DECISIONS_PER_PART)
                raw, api_ms = await self._client.post(body)
            answer = self._client.parse(raw, api_ms)
        except TimeoutError:
            reason = "deadline"
        except Thx02TimeoutError:
            reason = "timeout"
        except Thx02RateLimitedError as exc:
            reason = "rate_limited"
            if self._limiter is not None:
                self._limiter.pause(exc.retry_after_s)
        except (Thx02Error, ValueError) as exc:
            reason = f"error: {exc}"
        if self._recorder is not None:
            await self._recorder.record(
                part.part_id,
                body,
                response=raw,
                error=reason,
                latency_ms=api_ms if raw is not None else _ms_since(t0),
                model=self.cfg.model,
            )
        if answer is None:
            return self._fallback(part, reason or "no answer", t0)
        return _ai(part.part_id, answer, _ms_since(t0))

    @staticmethod
    def _fallback(part: PartRequest, reason: str, t0: float) -> Decision:
        _log.warning("part %d: THX-02 fallback (%s)", part.part_id, reason)
        return fallback_decision(part.part_id, reason=reason, latency_ms=_ms_since(t0))
