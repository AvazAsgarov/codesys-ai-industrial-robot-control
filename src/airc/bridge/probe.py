"""Check the bridge against the running soft-PLC: ``python -m airc.bridge.probe``.

Reads the PLC outputs once, then times 200 read+write cycles (inputs written back unchanged
except the heartbeat, with ``twin_active`` FALSE so the cell keeps its loopback feedback).
"""

import asyncio
import statistics
import time

from airc.bridge.client import BridgeClient
from airc.bridge.messages import ZERO6, PlcInputs
from airc.bridge.tags import TagMap
from airc.common.config import load_config

CYCLES = 200


async def main() -> None:
    """Run the probe and print the result."""
    endpoint = load_config().plc.opcua_endpoint
    client = BridgeClient(endpoint, TagMap.load())
    await client.ensure_connected(timeout_s=10.0)
    out = await client.read_outputs()
    print(f"PackML state {out.state}, mode {out.mode}, setpoint seq {out.setpoint_seq}")
    print(f"joint setpoints [deg] {out.joint_sp_deg}")
    times: list[float] = []
    for i in range(CYCLES):
        start = time.perf_counter()
        await client.read_outputs()
        await client.write_inputs(
            PlcInputs(
                heartbeat=bool(i % 2),
                twin_active=False,
                joint_fb_deg=out.joint_sp_deg,
                joint_torque_nm=ZERO6,
                feedback_seq=i,
                feedback_for_seq=out.setpoint_seq,
                pe1=False,
                pe2=False,
                vacuum_ok=False,
                bin_full=(False, False, False, False, False, False),
                door_closed=True,
                estop_ok=True,
            )
        )
        times.append((time.perf_counter() - start) * 1000.0)
    times.sort()
    print(
        f"{CYCLES} cycles: mean {statistics.mean(times):.2f} ms, "
        f"p95 {times[int(CYCLES * 0.95) - 1]:.2f} ms, max {times[-1]:.2f} ms"
    )
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
