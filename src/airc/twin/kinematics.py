"""Orientation conventions shared with the PLC (CODESYS SoftMotion, ``Kin_ArticulatedRobot_6DOF``).

Measured against CODESYS (``tests/fixtures/fk_reference.json``):

- Joint directions: J1 about +Z; J2 and J3 about -Y; J4 about +X (forearm); J5 about +Y; J6 about
  +X (tool axis), all in the twin's link frames (zero pose: upper arm up, forearm and tool forward).
- MCS orientation (A, B, C) are Z-Y-Z Euler angles in degrees of the *tool frame*, whose Z axis is
  the approach direction (the twin's flange X axis): ``R_tool = R_flange @ TOOL_FROM_FLANGE``.
"""

import math

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

JOINT_AXES: tuple[tuple[int, int, int], ...] = (
    (0, 0, 1),
    (0, -1, 0),
    (0, -1, 0),
    (1, 0, 0),
    (0, 1, 0),
    (1, 0, 0),
)

# columns: tool X, Y, Z expressed in the flange frame (tool Z = flange X)
TOOL_FROM_FLANGE: FloatArray = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])


def _rot(axis: int, deg: float) -> FloatArray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    if axis == 1:  # about Y
        return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])  # about Z


def zyz_to_matrix(a_deg: float, b_deg: float, c_deg: float) -> FloatArray:
    """Rotation matrix of CODESYS MCS angles A, B, C (Z-Y-Z Euler, degrees)."""
    return _rot(2, a_deg) @ _rot(1, b_deg) @ _rot(2, c_deg)


def rotation_angle_deg(r1: FloatArray, r2: FloatArray) -> float:
    """Angle of the relative rotation between two rotation matrices (degrees)."""
    cos = (float(np.trace(r1.T @ r2)) - 1.0) / 2.0
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))
