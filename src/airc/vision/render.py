"""Offscreen rendering of the inspection camera: RGB image plus exact per-pixel body ids.

A :class:`FrameRenderer` owns an OpenGL context: create and use it in one thread only. Domain
randomisation (spec §6.1: lighting, mild noise and blur) changes only the image, never the
physics or the ground truth.
"""

from dataclasses import dataclass

import mujoco
import numpy as np
from numpy.typing import NDArray

from airc.twin.config import TwinConfig

_GEOM = 5  # mjtObj.mjOBJ_GEOM in the segmentation image


@dataclass(frozen=True)
class Randomisation:
    """One draw of the image randomisation."""

    light_scale: float  # light intensity factor
    light_tilt_deg: tuple[float, float]  # light direction tilt about world x and y
    noise_sigma: float  # Gaussian pixel noise, in grey levels (0..255)
    blur_sigma_px: float  # Gaussian blur

    @classmethod
    def draw(cls, rng: np.random.Generator) -> "Randomisation":
        """Draw within the plan's ranges (light x0.6..1.4, +-30 deg, noise 2, blur 0..0.8 px)."""
        return cls(
            light_scale=float(rng.uniform(0.6, 1.4)),
            light_tilt_deg=(float(rng.uniform(-30, 30)), float(rng.uniform(-30, 30))),
            noise_sigma=2.0,
            blur_sigma_px=float(rng.uniform(0.0, 0.8)),
        )


@dataclass(frozen=True)
class Frame:
    """A rendered image and, per pixel, the MuJoCo body id seen there (-1: background)."""

    rgb: NDArray[np.uint8]
    bodies: NDArray[np.int32]

    def body_mask(self, body_id: int) -> NDArray[np.bool_]:
        """Pixels showing the given body."""
        return self.bodies == body_id


def _gaussian_blur(img: NDArray[np.float64], sigma: float) -> NDArray[np.float64]:
    if sigma <= 0.0:
        return img
    radius = max(1, round(3 * sigma))
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-(x**2) / (2 * sigma**2))
    kernel /= kernel.sum()
    out = img
    for axis in (0, 1):
        out = np.apply_along_axis(lambda m: np.convolve(m, kernel, mode="same"), axis, out)
    return out


def _rotate(direction: NDArray[np.float64], tilt_deg: tuple[float, float]) -> NDArray[np.float64]:
    ax, ay = np.radians(tilt_deg)
    rx = np.array([[1, 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]])
    ry = np.array([[np.cos(ay), 0, np.sin(ay)], [0, 1, 0], [-np.sin(ay), 0, np.cos(ay)]])
    d = ry @ rx @ direction
    return d / np.linalg.norm(d)


class FrameRenderer:
    """Renders one camera of a model offscreen."""

    def __init__(self, model: mujoco.MjModel, camera: str, cfg: TwinConfig | None = None) -> None:
        """Create the OpenGL context and buffers (in the calling thread).

        Args:
            model: The model (its offscreen buffer must be at least the image size).
            camera: Camera name.
            cfg: Twin configuration for the image size (default: ``config/twin.yaml``).
        """
        c = (cfg if cfg is not None else TwinConfig.load()).camera
        self.model = model
        self.camera = camera
        self._rgb = mujoco.Renderer(model, c.height_px, c.width_px)
        self._seg = mujoco.Renderer(model, c.height_px, c.width_px)
        self._seg.enable_segmentation_rendering()
        self._options = mujoco.MjvOption()
        self._options.geomgroup[:] = 1  # parts are in their own geom group

    def render(self, data: mujoco.MjData, rand: Randomisation | None = None) -> Frame:
        """Render the camera for the current state of ``data``."""
        self._seg.update_scene(data, camera=self.camera, scene_option=self._options)
        seg = self._seg.render()
        geom = np.where(seg[:, :, 1] == _GEOM, seg[:, :, 0], -1)
        bodies = np.where(geom >= 0, self.model.geom_bodyid[np.maximum(geom, 0)], -1)
        saved_dir = self.model.light_dir.copy()
        saved_diffuse = self.model.light_diffuse.copy()
        try:
            if rand is not None:
                for i in range(self.model.nlight):
                    self.model.light_dir[i] = _rotate(saved_dir[i], rand.light_tilt_deg)
                    self.model.light_diffuse[i] = np.clip(saved_diffuse[i] * rand.light_scale, 0, 1)
            self._rgb.update_scene(data, camera=self.camera, scene_option=self._options)
            rgb = self._rgb.render()
        finally:
            self.model.light_dir[:] = saved_dir
            self.model.light_diffuse[:] = saved_diffuse
        if rand is not None:
            img = _gaussian_blur(rgb.astype(np.float64), rand.blur_sigma_px)
            noise_rng = np.random.default_rng(int(rand.light_scale * 1e6))
            img = img + noise_rng.normal(0.0, rand.noise_sigma, img.shape)
            rgb = np.clip(np.round(img), 0, 255).astype(np.uint8)
        return Frame(rgb=rgb, bodies=bodies.astype(np.int32))

    def close(self) -> None:
        """Release the OpenGL resources."""
        self._rgb.close()
        self._seg.close()
