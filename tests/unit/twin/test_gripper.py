"""Suction gripper of the twin: weld only when the cup is close to the part top."""

import numpy as np

from airc.twin.twin import PartSpec, Twin

HOME_RAD = np.radians([0.0, -30.0, 60.0, 0.0, 60.0, 0.0])


def test_suction_welds_only_when_close() -> None:
    twin = Twin()
    pid = twin.spawn(PartSpec(cls=0, y_mm=0.0, theta_deg=0.0, x_mm=900.0))
    twin.step(HOME_RAD, 0.0, 0.0, False)
    twin.place_part_under_cup(pid, gap_mm=10.0)
    state = twin.step(twin.joint_positions_rad(), 0.0, 0.0, True)
    assert not state.vacuum_ok
    twin.place_part_under_cup(pid, gap_mm=3.0)
    state = twin.step(twin.joint_positions_rad(), 0.0, 0.0, True)
    assert state.vacuum_ok
    assert twin.part(pid).held


def test_held_part_follows_the_tool_and_drops_on_release() -> None:
    twin = Twin()
    pid = twin.spawn(PartSpec(cls=2, y_mm=0.0, theta_deg=0.0, x_mm=900.0))
    twin.step(HOME_RAD, 0.0, 0.0, False)
    twin.place_part_under_cup(pid, gap_mm=2.0)
    q = twin.joint_positions_rad()
    twin.step(q, 0.0, 0.0, True)
    z0 = twin.part(pid).z_mm
    lifted = q.copy()
    lifted[1] -= np.radians(8.0)  # shoulder back: the tool rises
    state = twin.state()
    for _ in range(40):
        state = twin.step(lifted, 0.0, 0.0, True)
    assert state.vacuum_ok
    assert twin.part(pid).z_mm > z0 + 20.0
    state = twin.state()
    for _ in range(40):
        state = twin.step(lifted, 0.0, 0.0, False)
    assert not state.vacuum_ok
    assert not twin.part(pid).held
    assert twin.part(pid).z_mm < z0 + 5.0  # fell back onto the belt
