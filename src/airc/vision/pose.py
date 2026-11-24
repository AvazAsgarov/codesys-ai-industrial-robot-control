"""Part pose in the image from its segmentation mask (spec §6.2): centroid and principal axis."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

ROUND_RATIO = 1.15  # principal axes this close in length: no defined orientation


@dataclass(frozen=True)
class MaskPose:
    """Centroid (u, v in pixels), orientation of the long axis and properties of a mask.

    ``theta_deg`` is in (-90, 90], counter-clockwise in the image (v points down) from +u.
    """

    u: float
    v: float
    theta_deg: float
    area_px: int
    round: bool  # no long axis: theta is meaningless
    touches_border: bool  # cut by the image edge: centroid and theta are biased


def mask_pose(mask: NDArray[np.bool_]) -> MaskPose:
    """Pose of the pixels set in ``mask`` (principal component analysis).

    Raises:
        ValueError: If the mask is empty.
    """
    vs, us = np.nonzero(mask)
    if us.size == 0:
        msg = "empty mask"
        raise ValueError(msg)
    u0, v0 = float(us.mean()), float(vs.mean())
    du, dv = us - u0, vs - v0
    cov = np.array([[np.mean(du * du), np.mean(du * dv)], [np.mean(du * dv), np.mean(dv * dv)]])
    values, vectors = np.linalg.eigh(cov)  # ascending
    major = vectors[:, 1]
    theta = float(np.degrees(np.arctan2(-major[1], major[0])))  # v down -> counter-clockwise
    theta = (theta + 90.0) % 180.0 - 90.0  # (-90, 90]
    if theta == -90.0:  # noqa: PLR2004 - the half-open interval's lower end
        theta = 90.0
    is_round = values[0] <= 0 or values[1] / values[0] < ROUND_RATIO**2
    border = bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())
    return MaskPose(
        u=u0, v=v0, theta_deg=theta, area_px=int(us.size), round=bool(is_round),
        touches_border=border,
    )  # fmt: skip
