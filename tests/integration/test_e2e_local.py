"""End to end on the real soft-PLC: PLC + OPC UA bridge + twin (Phase 2 exit test).

Local only (needs CODESYS Control Win): ``python tools/uv_run.py pytest -m codesys``.
Set ``AIRC_E2E_SKIP_DEPLOY=1`` to reuse an application already deployed with ``airc plc deploy``.
"""

import asyncio
import os
import re
from pathlib import Path

import pytest

from airc.bridge.client import BridgeClient
from airc.bridge.messages import PackMLCommand, PackMLState
from airc.bridge.tags import TagMap
from airc.common.config import load_config
from airc.plc import runtime
from airc.runner import Runner, RunReport, run_precise
from airc.twin.scenario import Scenario
from airc.twin.twin import Twin

pytestmark = pytest.mark.codesys

REPO = Path(__file__).resolve().parents[2]
RUN_S = float(os.environ.get("AIRC_E2E_SECONDS", "300"))
ALARMS = {
    int(v): k
    for k, v in re.findall(
        r"(\w+) := (\d+)", (REPO / "plc/src/Types/E_AlarmId.st").read_text(encoding="utf-8")
    )
}
EVENTS: list[str] = []  # PLC diagnostics when the cell left Execute


@pytest.fixture(scope="module")
def plc() -> str:
    settings = runtime.load_runtime_settings()
    runtime.start(settings)
    if not os.environ.get("AIRC_E2E_SKIP_DEPLOY"):
        runtime.deploy(settings, load_config().plc.project_file)
    return load_config().plc.opcua_endpoint


async def _wait_state(control: BridgeClient, wanted: PackMLState, timeout_s: float) -> None:
    for _ in range(int(timeout_s * 10)):
        if (await control.read_outputs()).state == wanted:
            return
        await asyncio.sleep(0.1)
    state = PackMLState((await control.read_outputs()).state)
    pytest.fail(f"PLC did not reach {wanted.name} within {timeout_s} s (state {state.name})")


async def _start_cell(control: BridgeClient) -> None:
    """Bring the cell from any state to Execute, as an operator would (Clear/Stop, Reset, Start)."""
    state = PackMLState((await control.read_outputs()).state)
    if state == PackMLState.ABORTED:
        await control.send_command(PackMLCommand.CLEAR)
        await _wait_state(control, PackMLState.STOPPED, 15)
    elif state != PackMLState.STOPPED:
        await control.send_command(PackMLCommand.STOP)
        await _wait_state(control, PackMLState.STOPPED, 30)
    await control.send_command(PackMLCommand.RESET)
    await _wait_state(control, PackMLState.IDLE, 15)
    await control.send_command(PackMLCommand.START)
    await _wait_state(control, PackMLState.EXECUTE, 60)


async def _production_run(endpoint: str, scenario: Scenario) -> tuple[RunReport, list[int]]:
    """Twin running, Reset + Start, run, return the report and the PLC states seen once a second."""
    tags = TagMap.load()
    twin = Twin(bin_capacity=scenario.bin_capacity)
    runner = Runner(
        BridgeClient(endpoint, tags, timeout_s=twin.cfg.bridge_timeout_s), twin, scenario
    )
    control = BridgeClient(endpoint, tags)
    await control.connect()
    stop = asyncio.Event()
    task = asyncio.create_task(runner.run(stop=stop))
    states: list[int] = []
    try:
        await asyncio.sleep(1.0)  # twin feedback flowing before the cell powers the robot
        await _start_cell(control)
        for k in range(int(RUN_S)):
            await asyncio.sleep(1.0)
            state = (await control.read_outputs()).state
            states.append(state)
            if state != PackMLState.EXECUTE and len(EVENTS) < 5:
                d = await control.read_diag()
                EVENTS.append(
                    f"t={k}s state={PackMLState(state).name} alarm={ALARMS.get(d.newest_alarm)} "
                    f"error={d.error_active} critical={d.critical_active} step={d.pick_step} "
                    f"worst joint={d.worst_joint} following error={d.following_error_deg}"
                )
        await control.send_command(PackMLCommand.STOP)
        for k in range(600):
            state = (await control.read_outputs()).state
            if state == PackMLState.STOPPED:
                break
            if state == PackMLState.ABORTED:
                d = await control.read_diag()
                runner_state = f"runner done={task.done()}"
                if task.done():
                    runner_state += f" error={task.exception()!r}"
                pytest.fail(
                    f"Stop ended in ABORTED after {k / 10:.1f} s: alarm "
                    f"{ALARMS.get(d.newest_alarm)}, step {d.pick_step}, {runner_state}"
                )
            await asyncio.sleep(0.1)
        else:
            pytest.fail("the cell did not stop within 60 s")
    finally:
        stop.set()
        report = await task
        await control.close()
    return report, states


def test_e2e_sorts_by_class(plc: str) -> None:
    scenario = Scenario.load(REPO / "config/scenarios/p2_demo.yaml")
    report, states = run_precise(_production_run(plc, scenario))
    placed = sum(report.bin_counts)
    print(  # visible with -s: the numbers for the docs
        f"\ncycles {report.cycles} overruns {report.overruns} "
        f"longest gap {report.max_gap_ms:.0f} ms"
        f"\nspawned {report.spawned} captures {report.captures} placed {placed} "
        f"bins {report.bin_counts} wrong {report.wrong_bin} missed {report.missed} "
        f"lost {report.lost}"
    )
    assert set(states) == {PackMLState.EXECUTE}, "left Execute:\n" + "\n".join(EVENTS)
    assert report.spawned >= RUN_S / 12.0  # one part per ~1000 mm at ~96 mm/s
    assert report.wrong_bin == 0
    assert report.lost == 0
    # parts still on the belt when the run ends are neither placed nor lost
    assert placed >= 0.95 * (report.spawned - 3)
    assert report.max_gap_ms < 200.0  # far below the PLC's 500 ms bridge watchdog


async def _faults_run(endpoint: str, scenario: Scenario) -> tuple[RunReport, list[str]]:
    """Run the fault scenario; recover from every abort as the operator would.

    Returns the report and one line per non-Execute episode: ``<state> <alarm> <recovery s>``.
    """
    tags = TagMap.load()
    twin = Twin(bin_capacity=scenario.bin_capacity)
    runner = Runner(
        BridgeClient(endpoint, tags, timeout_s=twin.cfg.bridge_timeout_s), twin, scenario
    )
    control = BridgeClient(endpoint, tags)
    await control.connect()
    stop = asyncio.Event()
    task = asyncio.create_task(runner.run(stop=stop))
    episodes: list[str] = []
    loop = asyncio.get_running_loop()
    try:
        await asyncio.sleep(1.0)
        await _start_cell(control)
        end = loop.time() + (scenario.duration_s or 300.0) - 5.0
        while loop.time() < end:
            await asyncio.sleep(0.25)
            state = PackMLState((await control.read_outputs()).state)
            if state == PackMLState.EXECUTE:
                continue
            alarm = ALARMS.get((await control.read_diag()).newest_alarm)
            t0 = loop.time()
            if state == PackMLState.ABORTED:
                await asyncio.sleep(3.0)  # the fault clears (E-stop released, door closed, ...)
                await _start_cell(control)
            else:  # Suspended (bin full) and its transitions resume by themselves
                await _wait_state(control, PackMLState.EXECUTE, 60)
            episodes.append(f"{state.name} {alarm} {loop.time() - t0:.0f}")
        await control.send_command(PackMLCommand.STOP)
        await _wait_state(control, PackMLState.STOPPED, 60)
    finally:
        stop.set()
        report = await task
        await control.close()
    return report, episodes


def test_e2e_faults_abort_and_recover(plc: str) -> None:
    scenario = Scenario.load(REPO / "config/scenarios/p2_faults.yaml")
    report, episodes = run_precise(_faults_run(plc, scenario))
    print(  # visible with -s
        "\n" + "\n".join(episodes) + f"\nbins {report.bin_counts} wrong {report.wrong_bin} "
        f"missed {report.missed} lost {report.lost} reconnects {report.reconnects}"
    )
    seen = " ".join(episodes)
    for fault in ("EStop", "BridgeLost", "DoorOpen"):  # each Critical fault aborted the cell
        assert f"ABORTED {fault}" in seen, seen
    assert "SUSPENDED" in seen or "SUSPENDING" in seen, seen  # the full bin suspended it
    assert report.lost == 0
    # a part held during an abort goes to Quarantine on restart; no other part is misplaced
    assert report.wrong_bin <= report.bin_counts[5]
