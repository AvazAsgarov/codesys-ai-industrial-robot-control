"""Simulated servo drives of the twin: tracking, overshoot and stall."""

import numpy as np

from airc.twin.twin import Twin

HOME_DEG = np.array([0.0, -30.0, 60.0, 0.0, 60.0, 0.0])
CYCLE_S = 0.02


def _ramp(twin: Twin, speed_deg_s: float, seconds: float) -> tuple[list[float], np.ndarray]:
    """J1 ramps from HOME; returns J1 lag per cycle [deg] and the final setpoint [deg]."""
    sp = HOME_DEG.copy()
    lags: list[float] = []
    for _ in range(round(seconds / CYCLE_S)):
        sp[0] += speed_deg_s * CYCLE_S
        state = twin.step(np.radians(sp), 0.0, 0.0, False)
        lags.append(sp[0] - float(np.degrees(state.joint_pos_rad[0])))
    return lags, sp


def _settle(twin: Twin) -> None:
    twin.set_joint_positions(np.radians(HOME_DEG))
    for _ in range(25):
        twin.step(np.radians(HOME_DEG), 0.0, 0.0, False)


def test_servo_tracks_ramp() -> None:
    twin = Twin()
    _settle(twin)
    lags, sp = _ramp(twin, 90.0, 1.0)
    assert max(abs(v) for v in lags[-10:]) <= 2.0  # steady lag at 90 deg/s
    overshoot = 0.0
    state = twin.state()
    for k in range(10):  # the PLC brakes with a ramp (here 450 deg/s^2), then holds
        sp[0] += 90.0 * CYCLE_S * (9 - k) / 10
        state = twin.step(np.radians(sp), 0.0, 0.0, False)
    for _ in range(50):  # no overshoot beyond 0.5 deg
        state = twin.step(np.radians(sp), 0.0, 0.0, False)
        overshoot = max(overshoot, float(np.degrees(state.joint_pos_rad[0])) - sp[0])
    assert overshoot <= 0.5
    assert abs(float(np.degrees(state.joint_pos_rad[0])) - sp[0]) <= 0.2


def test_blocked_joint_stalls_at_torque_limit() -> None:
    twin = Twin()
    _settle(twin)
    twin.set_joint_damping(0, 1e7)  # J1 blocked
    lags, _ = _ramp(twin, 90.0, 0.6)
    limit = twin.cfg.servo.torque_limit[0]
    assert lags[-1] > 40.0  # the joint does not follow
    assert abs(float(twin.state().joint_torque_nm[0])) == np.float64(limit)
