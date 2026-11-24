"""Pinhole model of a camera: projection of world points, back-projection onto the belt.

Conventions: world frame = MuJoCo world (m); the camera frame is MuJoCo's (x right, y up, looking
along -z); image pixels have u to the right and v downwards, (0, 0) at the top-left corner.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
import yaml
from numpy.typing import NDArray

from airc.twin.cell import CellGeometry

MM = 0.001
FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class CameraModel:
    """Intrinsics ``k`` (3x3, pixels) and pose (``r_wc`` camera axes in world, ``position_m``)."""

    k: FloatArray
    r_wc: FloatArray
    position_m: FloatArray
    width: int
    height: int

    @classmethod
    def from_mujoco(
        cls,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        name: str,
        size: tuple[int, int] | None = None,
    ) -> "CameraModel":
        """The exact model of a MuJoCo camera (needs ``mj_forward`` to have run).

        Args:
            model: The MuJoCo model.
            data: Its data (camera pose).
            name: Camera name.
            size: Image (width, height) in pixels; default: the inspection camera's
                (``config/twin.yaml``).
        """
        if size is None:
            from airc.twin.config import TwinConfig  # noqa: PLC0415 - avoids a cycle

            c = TwinConfig.load().camera
            size = (c.width_px, c.height_px)
        width, height = size
        cam = model.camera(name).id
        f = (height / 2) / np.tan(np.radians(float(model.cam_fovy[cam])) / 2)
        k = np.array([[f, 0.0, width / 2], [0.0, f, height / 2], [0.0, 0.0, 1.0]])
        return cls(
            k=k,
            r_wc=data.cam_xmat[cam].reshape(3, 3).copy(),
            position_m=data.cam_xpos[cam].copy(),
            width=width,
            height=height,
        )

    @classmethod
    def load(cls, path: Path) -> "CameraModel":
        """A calibrated model saved by :meth:`save`."""
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            k=np.array(raw["k"], dtype=np.float64),
            r_wc=np.array(raw["r_wc"], dtype=np.float64),
            position_m=np.array(raw["position_m"], dtype=np.float64),
            width=int(raw["width"]),
            height=int(raw["height"]),
        )

    def save(self, path: Path, note: str = "") -> None:
        """Write the model as JSON (which :meth:`load` reads as YAML); ``note``: its origin."""
        data: dict[str, object] = {
            "note": note,
            "width": self.width,
            "height": self.height,
            "k": self.k.round(6).tolist(),
            "r_wc": self.r_wc.round(9).tolist(),
            "position_m": self.position_m.round(9).tolist(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")  # YAML reads JSON

    @property
    def forward(self) -> FloatArray:
        """Viewing direction in world (unit vector)."""
        return -self.r_wc[:, 2]

    def project(self, world_m: FloatArray) -> tuple[float, float]:
        """Pixel (u, v) of a world point.

        Raises:
            ValueError: If the point is behind the camera.
        """
        p = self.r_wc.T @ (np.asarray(world_m, dtype=np.float64) - self.position_m)
        depth = -p[2]
        if depth <= 0.0:
            msg = "point is behind the camera"
            raise ValueError(msg)
        u = self.k[0, 2] + self.k[0, 0] * p[0] / depth
        v = self.k[1, 2] - self.k[1, 1] * p[1] / depth
        return float(u), float(v)

    def ray(self, u: float, v: float) -> tuple[FloatArray, FloatArray]:
        """World origin and unit direction of the viewing ray through pixel (u, v)."""
        d_cam = np.array(
            [(u - self.k[0, 2]) / self.k[0, 0], -(v - self.k[1, 2]) / self.k[1, 1], -1.0]
        )
        d = self.r_wc @ d_cam
        return self.position_m.copy(), d / np.linalg.norm(d)

    def pixel_to_belt(
        self, u: float, v: float, z_mm: float, geo: CellGeometry
    ) -> tuple[float, float]:
        """Belt-frame (x, y) in mm where the ray through (u, v) meets a plane above the belt.

        ``z_mm`` is the plane's height above the belt surface (e.g. the seen part's centre).
        """
        origin, d = self.ray(u, v)
        plane_z = (geo.belt_surface_z + z_mm) * MM
        if abs(d[2]) < 1e-9:  # noqa: PLR2004 - a ray parallel to the belt never meets it
            msg = "viewing ray is parallel to the belt"
            raise ValueError(msg)
        t = (plane_z - origin[2]) / d[2]
        hit = origin + t * d
        return float(hit[0] / MM - geo.belt_origin_x), float(hit[1] / MM - geo.belt_origin_y)

    def pixels_to_belt(
        self, us: FloatArray, vs: FloatArray, z_mm: float, geo: CellGeometry
    ) -> FloatArray:
        """:meth:`pixel_to_belt` for many pixels at once: an ``(n, 2)`` array of belt x, y (mm)."""
        u = np.asarray(us, dtype=np.float64)
        v = np.asarray(vs, dtype=np.float64)
        d_cam = np.stack(
            [
                (u - self.k[0, 2]) / self.k[0, 0],
                -(v - self.k[1, 2]) / self.k[1, 1],
                -np.ones_like(u),
            ],
            axis=1,
        )
        d = d_cam @ self.r_wc.T
        t = ((geo.belt_surface_z + z_mm) * MM - self.position_m[2]) / d[:, 2]
        hit = self.position_m + t[:, None] * d
        return np.stack([hit[:, 0] / MM - geo.belt_origin_x, hit[:, 1] / MM - geo.belt_origin_y], 1)
