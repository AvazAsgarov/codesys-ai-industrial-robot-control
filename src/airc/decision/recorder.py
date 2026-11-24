"""Record every THX-02 exchange and replay runs from the recording (spec 7.4).

One JSON line per part: run id, scenario seed, part id, UTC timestamp, requested and answering
model, latency, the SHA-256 of the exact request bytes, the request with each image replaced by
``sha256:<hex>`` of its bytes (the images themselves are not stored), and either the raw
response or the reason the rule fallback was used. Paper numbers are computed from these files.
"""

import asyncio
import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self, cast

from airc.decision.thx02 import encode_body

Json = dict[str, Any]


def payload_sha256(body: Mapping[str, Any]) -> str:
    """SHA-256 (hex) of the request bytes the client sends for ``body``."""
    return hashlib.sha256(encode_body(body)).hexdigest()


def _image_ref(image: object) -> str:
    text = str(image)
    data = text.split(",", 1)[1] if text.startswith("data:") else text
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raw = text.encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _without_images(body: Mapping[str, Any]) -> Json:
    out = dict(body)
    images = out.get("images")
    if isinstance(images, list):
        out["images"] = [_image_ref(i) for i in cast("list[object]", images)]
    return out


@dataclass(frozen=True)
class Exchange:
    """One recorded request and its outcome."""

    run_id: str
    seed: int | None
    part_id: int
    timestamp: str
    model: str
    response_model: str | None
    latency_ms: float
    payload_sha256: str
    request: Json
    response: Json | None
    error: str | None  # the fallback reason when there is no usable response

    @classmethod
    def from_json(cls, data: Json) -> Self:
        """Rebuild an exchange from its JSON line (raises ``KeyError``/``TypeError``)."""
        return cls(
            run_id=str(data["run_id"]),
            seed=None if data["seed"] is None else int(data["seed"]),
            part_id=int(data["part_id"]),
            timestamp=str(data["timestamp"]),
            model=str(data["model"]),
            response_model=None if data["response_model"] is None else str(data["response_model"]),
            latency_ms=float(data["latency_ms"]),
            payload_sha256=str(data["payload_sha256"]),
            request=cast("Json", data["request"]),
            response=cast("Json | None", data["response"]),
            error=None if data["error"] is None else str(data["error"]),
        )


class Recorder:
    """Appends exchanges to a JSONL file without blocking the event loop."""

    def __init__(self, path: Path, *, run_id: str, seed: int | None = None) -> None:
        """Create a recorder (the file and its folder are created on the first record).

        Args:
            path: JSONL file to append to.
            run_id: Identifies the run (also the replay key across files).
            seed: The scenario seed of the run.
        """
        self.path = path
        self.run_id = run_id
        self.seed = seed
        self._lock = asyncio.Lock()

    async def record(  # noqa: PLR0913 - one record's fields
        self,
        part_id: int,
        body: Mapping[str, Any],
        *,
        response: Json | None = None,
        error: str | None = None,
        latency_ms: float,
        model: str = "",
    ) -> Exchange:
        """Append one exchange.

        Args:
            part_id: The PLC's part id.
            body: The request body as sent.
            response: The raw response, if one was received.
            error: Why the fallback was used, if it was.
            latency_ms: Round-trip latency (or time until the fallback).
            model: The model id that was requested.

        Returns:
            The recorded exchange.
        """
        response_model = response.get("model") if response is not None else None
        exchange = Exchange(
            run_id=self.run_id,
            seed=self.seed,
            part_id=part_id,
            timestamp=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            model=model,
            response_model=None if response_model is None else str(response_model),
            latency_ms=latency_ms,
            payload_sha256=payload_sha256(body),
            request=_without_images(body),
            response=response,
            error=error,
        )
        line = json.dumps(asdict(exchange), ensure_ascii=False) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append, line)
        return exchange

    def _append(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)


class ReplaySource:
    """Answers from a recording: by request hash, else by part id (the last record wins)."""

    def __init__(self, exchanges: list[Exchange]) -> None:
        """Index the exchanges."""
        self._by_hash = {e.payload_sha256: e for e in exchanges}
        self._by_part = {e.part_id: e for e in exchanges}
        self._count = len(exchanges)

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read a JSONL recording.

        Raises:
            ValueError: If a line is not a valid exchange (the message names file and line).
        """
        exchanges: list[Exchange] = []
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                exchanges.append(Exchange.from_json(json.loads(line)))
            except (ValueError, KeyError, TypeError) as exc:
                msg = f"{path.name}:{n}: not a recorded exchange: {exc!r}"
                raise ValueError(msg) from exc
        return cls(exchanges)

    def __len__(self) -> int:
        """Number of recorded exchanges."""
        return self._count

    def lookup(self, payload_sha256: str, part_id: int) -> Exchange | None:
        """The recorded exchange for this request, or ``None``.

        The request hash matches when the crop bytes are identical; the part id is the fallback
        for a re-run of the same seed whose renders differ in the last bit.
        """
        return self._by_hash.get(payload_sha256) or self._by_part.get(part_id)
