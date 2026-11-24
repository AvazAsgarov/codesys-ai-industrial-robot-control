"""BridgeClient against an in-process OPC UA server shaped like the PLC."""

import asyncio

import pytest

from airc.bridge.client import BridgeClient, BridgeDisconnectedError
from airc.bridge.messages import PlcInputs, VisionMsg
from airc.bridge.tags import TagMap
from tests.integration.fake_plc import FakePlc, free_port

INPUTS = PlcInputs(
    heartbeat=True,
    twin_active=True,
    joint_fb_deg=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
    joint_torque_nm=(0.5, 0.5, 0.5, 0.5, 0.5, 0.5),
    feedback_seq=7,
    feedback_for_seq=5,
    pe1=True,
    pe2=False,
    vacuum_ok=False,
    bin_full=(False, True, False, False, False, False),
    door_closed=True,
    estop_ok=True,
)


def test_round_trip_outputs_and_inputs() -> None:
    async def scenario() -> None:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            await plc.set("joint_sp_deg", [10.0, -20.0, 30.0, 0.0, 45.0, 0.0])
            await plc.set("setpoint_seq", 42)
            await plc.set("belt_pos_mm", 123.5)
            await plc.set("state", 6)
            await plc.set("capture.seq", 3)
            await plc.set("capture.part_id", 9)
            client = BridgeClient(plc.endpoint, TagMap.load())
            await client.connect()
            out = await client.read_outputs()
            assert out.joint_sp_deg == (10.0, -20.0, 30.0, 0.0, 45.0, 0.0)
            assert out.setpoint_seq == 42
            assert out.belt_pos_mm == pytest.approx(123.5)
            assert out.state == 6
            assert (out.capture.seq, out.capture.part_id) == (3, 9)
            await client.write_inputs(INPUTS)
            assert await plc.get("joint_fb_deg") == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
            assert await plc.get("feedback_for_seq") == 5
            assert await plc.get("bin_full") == [False, True, False, False, False, False]
            assert await plc.get("twin_active") is True
            await client.close()
        finally:
            await plc.stop()

    asyncio.run(scenario())


def test_vision_seq_written_last() -> None:
    async def scenario() -> None:
        plc = FakePlc(free_port(), TagMap.load())
        await plc.start()
        try:
            client = BridgeClient(plc.endpoint, TagMap.load())
            await client.connect()
            vision = VisionMsg(
                seq=1,
                part_id=9,
                valid=True,
                cls=2,
                confidence=0.9,
                x_mm=300.0,
                y_mm=-10.0,
                theta_deg=15.0,
            )
            await client.write_vision(vision)
            assert await plc.get("vision.part_id") == 9
            assert await plc.get("vision.cls") == 2
            assert plc.write_log[-1] == "vision.seq"
            assert "vision.part_id" in plc.write_log[:-1]
            await client.close()
        finally:
            await plc.stop()

    asyncio.run(scenario())


def test_reconnects_after_server_restart() -> None:
    async def scenario() -> None:
        port = free_port()
        plc = FakePlc(port, TagMap.load())
        await plc.start()
        client = BridgeClient(plc.endpoint, TagMap.load(), backoff_s=(0.2, 0.5))
        await client.connect()
        await plc.stop()
        with pytest.raises(BridgeDisconnectedError):
            await client.read_outputs()
        plc = FakePlc(port, TagMap.load())
        await plc.start()
        try:
            await plc.set("setpoint_seq", 77)
            await client.ensure_connected(timeout_s=10.0)
            assert (await client.read_outputs()).setpoint_seq == 77
            await client.close()
        finally:
            await plc.stop()

    asyncio.run(scenario())
