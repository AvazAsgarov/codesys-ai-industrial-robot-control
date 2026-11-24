"""Preparation of scanned parts (tools/fetch_objects.py): pose, centre, size, grip height."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "fetch_objects.py"


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fetch_objects", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def _box(lo: tuple[float, float, float], hi: tuple[float, float, float]):
    """Closed box mesh (metres): 8 vertices, 12 triangles."""
    x = [lo[0], hi[0]]
    y = [lo[1], hi[1]]
    z = [lo[2], hi[2]]
    v = np.array([[x[i], y[j], z[k]] for i in (0, 1) for j in (0, 1) for k in (0, 1)])
    f = np.array(
        [
            [0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
            [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3],
        ]
    )  # fmt: skip
    return v, f


def test_prepare_recentres_on_the_top_view_and_keeps_size() -> None:
    v, f = _box((0.10, 0.20, 0.0), (0.16, 0.24, 0.03))  # 60 x 40 x 30 mm, off-centre
    part = _tool().prepare(v, f, None, (0.0, 0.0, 0.0), 1.0)
    assert part.size_mm == pytest.approx((60.0, 40.0, 30.0), abs=0.01)
    assert part.vertices[:, 0].min() == pytest.approx(-0.030, abs=0.0011)
    assert part.vertices[:, 1].min() == pytest.approx(-0.020, abs=0.0011)
    assert part.vertices[:, 2].min() == pytest.approx(-0.015, abs=1e-9)
    assert part.grip_height_mm == pytest.approx(30.0, abs=0.01)


def test_prepare_turns_the_scan_into_its_resting_pose_and_scale() -> None:
    v, f = _box((0.0, 0.0, 0.0), (0.010, 0.020, 0.040))  # standing 10 x 20 x 40 mm
    part = _tool().prepare(v, f, None, (90.0, 0.0, 0.0), 0.5)  # lying, half size
    assert part.size_mm == pytest.approx((5.0, 20.0, 10.0), abs=0.01)
    assert part.grip_height_mm == pytest.approx(10.0, abs=0.01)


def test_grip_height_is_the_surface_under_the_cup_not_the_highest_point() -> None:
    base, fb = _box((0.0, 0.0, 0.0), (0.060, 0.060, 0.020))  # 20 mm slab
    post, fp = _box((0.0, 0.0, 0.020), (0.010, 0.010, 0.060))  # 40 mm post in a corner
    v = np.vstack([base, post])
    f = np.vstack([fb, fp + len(base)])
    part = _tool().prepare(v, f, None, (0.0, 0.0, 0.0), 1.0)
    assert part.size_mm[2] == pytest.approx(60.0, abs=0.01)
    assert part.grip_height_mm == pytest.approx(20.0, abs=0.01)


def test_part_hollow_at_its_centre_is_rejected() -> None:
    left, fl = _box((0.0, 0.0, 0.0), (0.010, 0.050, 0.020))
    right, fr = _box((0.040, 0.0, 0.0), (0.050, 0.050, 0.020))
    v = np.vstack([left, right])
    f = np.vstack([fl, fr + len(left)])
    with pytest.raises(ValueError, match="no surface"):
        _tool().prepare(v, f, None, (0.0, 0.0, 0.0), 1.0)
