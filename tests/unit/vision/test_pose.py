"""Part pose from a segmentation mask: centroid and principal axis."""

import numpy as np
import pytest

from airc.vision.pose import mask_pose


def _rotated_rect(  # noqa: PLR0913, PLR0917 - a rectangle's full description
    w: int, h: int, cx: float, cy: float, length: float, width: float, deg: float
):
    v, u = np.mgrid[0:h, 0:w]
    t = np.radians(deg)
    du, dv = u - cx, v - cy
    along = du * np.cos(t) - dv * np.sin(t)  # image v points down: +deg turns counter-clockwise
    across = du * np.sin(t) + dv * np.cos(t)
    return (np.abs(along) <= length / 2) & (np.abs(across) <= width / 2)


@pytest.mark.parametrize("deg", [0.0, 25.0, -40.0, 89.0])
def test_mask_pose_of_rotated_rectangle(deg: float) -> None:
    mask = _rotated_rect(400, 300, 210.0, 140.0, 120.0, 40.0, deg)
    pose = mask_pose(mask)
    assert pose.u == pytest.approx(210.0, abs=0.5)
    assert pose.v == pytest.approx(140.0, abs=0.5)
    err = (pose.theta_deg - deg + 90.0) % 180.0 - 90.0
    assert abs(err) < 1.0
    assert not pose.round
    assert not pose.touches_border


def test_mask_pose_round_is_flagged() -> None:
    v, u = np.mgrid[0:200, 0:200]
    disc = (u - 100) ** 2 + (v - 90) ** 2 <= 40**2
    pose = mask_pose(disc)
    assert pose.round
    assert pose.u == pytest.approx(100.0, abs=0.5)


def test_border_mask_flagged() -> None:
    mask = _rotated_rect(400, 300, 30.0, 140.0, 120.0, 40.0, 0.0)  # cut by the left edge
    assert mask_pose(mask).touches_border


def test_empty_mask_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        mask_pose(np.zeros((10, 10), dtype=bool))
