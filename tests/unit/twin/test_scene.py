"""MuJoCo cell scene: geometry from the PLC sources, belt transport (headless)."""

import numpy as np
import pytest

from airc.twin.cell import CellGeometry
from airc.twin.config import TwinConfig
from airc.twin.twin import PartSpec, Twin

HOME_RAD = np.radians([0.0, -30.0, 60.0, 0.0, 60.0, 0.0])


def test_geometry_comes_from_the_plc_sources() -> None:
    geo = CellGeometry.from_plc_sources()
    assert (geo.robot_a1, geo.robot_d1, geo.robot_a2) == (50.0, 400.0, 450.0)
    assert (geo.robot_a3, geo.robot_d3, geo.robot_d4, geo.robot_d6) == (50.0, 0.0, 450.0, 120.0)
    assert (geo.belt_origin_x, geo.belt_origin_y) == (-1500.0, -550.0)
    assert (geo.pe1_x, geo.pe2_x, geo.pick_window_end_x) == (300.0, 1050.0, 1750.0)
    assert len(geo.bin_drop_xy) == 6
    assert geo.bin_drop_xy[0] == (-500.0, 550.0)


def test_scene_loads_and_has_six_joints() -> None:
    twin = Twin()
    names = [twin.model.joint(i).name for i in range(twin.model.njnt)]
    assert names[:6] == ["j1", "j2", "j3", "j4", "j5", "j6"]
    assert twin.model.nu == 6


def test_part_on_belt_moves_with_belt_delta() -> None:
    twin = Twin()
    pid = twin.spawn(PartSpec(cls=0, y_mm=0.0, theta_deg=0.0, x_mm=100.0))
    twin.step(HOME_RAD, belt_pos_m=0.0, belt_vel_m_s=0.0, vacuum_on=False)
    x0 = twin.part(pid).x_mm
    for k in range(1, 11):  # 100 mm in 0.2 s
        twin.step(HOME_RAD, belt_pos_m=0.01 * k, belt_vel_m_s=0.5, vacuum_on=False)
    assert twin.part(pid).x_mm - x0 == pytest.approx(100.0, abs=1.0)


def test_parts_stop_with_belt() -> None:
    twin = Twin()
    pid = twin.spawn(PartSpec(cls=1, y_mm=20.0, theta_deg=10.0, x_mm=500.0))
    for _ in range(5):
        twin.step(HOME_RAD, belt_pos_m=0.0, belt_vel_m_s=0.0, vacuum_on=False)
    x0 = twin.part(pid).x_mm
    for _ in range(25):
        twin.step(HOME_RAD, belt_pos_m=0.0, belt_vel_m_s=0.0, vacuum_on=False)
    assert twin.part(pid).x_mm == pytest.approx(x0, abs=0.5)
    assert twin.part(pid).on_belt


def test_bridge_request_timeout_below_plc_watchdog() -> None:
    # a stalled OPC UA request must end (and reconnect) before the PLC's 500 ms bridge watchdog
    cfg = TwinConfig.load()
    assert cfg.bridge_period_s < cfg.bridge_timeout_s < 0.5
