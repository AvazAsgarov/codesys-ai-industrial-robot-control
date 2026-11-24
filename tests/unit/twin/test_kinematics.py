"""The twin's arm reproduces the PLC kinematics (fixture captured from CODESYS SoftMotion)."""

import json
from pathlib import Path

import numpy as np
import pytest

from airc.twin.kinematics import rotation_angle_deg, zyz_to_matrix
from airc.twin.twin import Twin

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "fk_reference.json"
POSES = json.loads(FIXTURE.read_text(encoding="utf-8"))["poses"]


@pytest.mark.parametrize("pose", POSES, ids=[str(p["acs_deg"]) for p in POSES])
def test_fk_matches_plc(pose: dict[str, object]) -> None:
    twin = Twin()
    acs = np.radians(np.array(pose["acs_deg"], dtype=float))
    twin.set_joint_positions(acs)
    mcs = pose["mcs"]
    assert isinstance(mcs, dict)
    expected = np.array([mcs["x"], mcs["y"], mcs["z"]], dtype=float)
    assert np.linalg.norm(twin.tcp_position_m() * 1000.0 - expected) <= 0.5
    rot = zyz_to_matrix(float(mcs["a"]), float(mcs["b"]), float(mcs["c"]))
    assert rotation_angle_deg(twin.tool_rotation(), rot) <= 0.1
