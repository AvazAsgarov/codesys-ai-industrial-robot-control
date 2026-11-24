"""Async OPC UA client for the PLC's ``GVL_Bridge`` (ADR 0003, ADR 0008).

One cycle is one batched read of the PLC outputs and one batched write of the inputs. A message
(vision, later decision) is written member by member in one request and its ``seq`` in a second
request, so the PLC never sees a new sequence number with old members.
"""

import asyncio
import contextlib
from collections.abc import Sequence
from typing import Any, cast

from asyncua import ua
from asyncua.client.client import Client
from asyncua.common.node import Node

from airc.bridge.messages import CaptureMsg, PlcInputs, PlcOutputs, Six, VisionMsg
from airc.bridge.tags import TagMap

OUTPUT_TAGS = (
    "joint_sp_deg",
    "setpoint_seq",
    "belt_pos_mm",
    "belt_vel_mm_s",
    "vacuum_on",
    "state",
    "mode",
    "capture.seq",
    "capture.part_id",
    "capture.belt_pos_mm",
)
INPUT_TAGS = (
    "heartbeat",
    "twin_active",
    "joint_fb_deg",
    "joint_torque_nm",
    "feedback_seq",
    "feedback_for_seq",
    "pe1",
    "pe2",
    "vacuum_ok",
    "bin_full",
    "door_closed",
    "estop_ok",
)
VISION_MEMBERS = (
    "vision.part_id",
    "vision.valid",
    "vision.cls",
    "vision.confidence",
    "vision.x_mm",
    "vision.y_mm",
    "vision.theta_deg",
)
_COMM_ERRORS = (OSError, TimeoutError, asyncio.TimeoutError, ua.UaError, ConnectionError)


class BridgeDisconnectedError(ConnectionError):
    """The OPC UA connection to the PLC is lost; call :meth:`BridgeClient.ensure_connected`."""


def _six(value: object) -> Six:
    seq = cast("Sequence[float]", value)
    return (seq[0], seq[1], seq[2], seq[3], seq[4], seq[5])


class BridgeClient:
    """Reads PLC outputs and writes PLC inputs over OPC UA."""

    def __init__(
        self,
        endpoint: str,
        tags: TagMap,
        timeout_s: float = 2.0,
        backoff_s: tuple[float, float] = (0.5, 8.0),
    ) -> None:
        """Create a client (not connected yet).

        Args:
            endpoint: OPC UA endpoint of the PLC, e.g. ``opc.tcp://127.0.0.1:4840``.
            tags: The tag map.
            timeout_s: Request timeout.
            backoff_s: First and maximum delay between reconnect attempts.
        """
        self._endpoint = endpoint
        self._tags = tags
        self._timeout_s = timeout_s
        self._backoff_s = backoff_s
        self._client: Client | None = None
        self._nodes: dict[str, Node] = {}

    @property
    def connected(self) -> bool:
        """True while a session is open."""
        return self._client is not None

    async def connect(self) -> None:
        """Open a session and resolve every tag's node."""
        client = Client(self._endpoint, timeout=self._timeout_s)
        await client.connect()
        self._client = client
        self._nodes = {name: client.get_node(self._tags.node_id(name)) for name in self._tags.tags}

    async def ensure_connected(self, timeout_s: float | None = None) -> None:
        """Reconnect with exponential backoff until connected (or ``timeout_s`` passes).

        Raises:
            BridgeDisconnectedError: If no connection could be made within ``timeout_s``.
        """
        if self._client is not None:
            return
        loop = asyncio.get_running_loop()
        deadline = None if timeout_s is None else loop.time() + timeout_s
        delay, max_delay = self._backoff_s
        while True:
            try:
                await self.connect()
                return
            except _COMM_ERRORS as exc:
                if deadline is not None and loop.time() + delay > deadline:
                    msg = f"PLC not reachable at {self._endpoint}"
                    raise BridgeDisconnectedError(msg) from exc
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)

    async def close(self) -> None:
        """Close the session (ignores errors of an already dead connection)."""
        client, self._client = self._client, None
        if client is not None:
            with contextlib.suppress(*_COMM_ERRORS):
                await client.disconnect()

    async def _lost(self, exc: BaseException) -> BridgeDisconnectedError:
        client, self._client = self._client, None
        if client is not None:
            with contextlib.suppress(*_COMM_ERRORS):
                await client.disconnect()
        return BridgeDisconnectedError(f"connection to the PLC lost: {exc}")

    def _require(self) -> Client:
        if self._client is None:
            msg = "not connected to the PLC"
            raise BridgeDisconnectedError(msg)
        return self._client

    async def read_outputs(self) -> PlcOutputs:
        """Read every PLC output in one request."""
        client = self._require()
        try:
            values: list[Any] = await client.read_values([self._nodes[n] for n in OUTPUT_TAGS])
        except _COMM_ERRORS as exc:
            raise await self._lost(exc) from exc
        v = dict(zip(OUTPUT_TAGS, values, strict=True))
        return PlcOutputs(
            joint_sp_deg=_six(v["joint_sp_deg"]),
            setpoint_seq=int(v["setpoint_seq"]),
            belt_pos_mm=float(v["belt_pos_mm"]),
            belt_vel_mm_s=float(v["belt_vel_mm_s"]),
            vacuum_on=bool(v["vacuum_on"]),
            state=int(v["state"]),
            mode=int(v["mode"]),
            capture=CaptureMsg(
                seq=int(v["capture.seq"]),
                part_id=int(v["capture.part_id"]),
                belt_pos_mm=float(v["capture.belt_pos_mm"]),
            ),
        )

    def _value(self, name: str, value: object) -> ua.DataValue:
        variant = getattr(ua.VariantType, self._tags.tags[name].variant)
        return ua.DataValue(ua.Variant(value, variant))

    async def _write(self, names: Sequence[str], values: Sequence[object]) -> None:
        client = self._require()
        try:
            await client.write_values(
                [self._nodes[n] for n in names],
                [self._value(n, v) for n, v in zip(names, values, strict=True)],
            )
        except _COMM_ERRORS as exc:
            raise await self._lost(exc) from exc

    async def write_inputs(self, inp: PlcInputs) -> None:
        """Write every PLC input in one request."""
        values: list[object] = [
            inp.heartbeat,
            inp.twin_active,
            list(inp.joint_fb_deg),
            list(inp.joint_torque_nm),
            inp.feedback_seq,
            inp.feedback_for_seq,
            inp.pe1,
            inp.pe2,
            inp.vacuum_ok,
            list(inp.bin_full),
            inp.door_closed,
            inp.estop_ok,
        ]
        await self._write(INPUT_TAGS, values)

    async def write_vision(self, msg: VisionMsg) -> None:
        """Write a vision message: members first, then its sequence number."""
        await self._write(
            VISION_MEMBERS,
            [msg.part_id, msg.valid, msg.cls, msg.confidence, msg.x_mm, msg.y_mm, msg.theta_deg],
        )
        await self._write(("vision.seq",), [msg.seq])
