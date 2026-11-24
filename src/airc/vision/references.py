"""Reference scenes for YOLOE visual prompts: renders of every part type from the twin.

A visual prompt is an example of each class (an image and the boxes of the examples in it).
YOLOE turns the examples into embeddings; averaged over several seeded views they stand for the
class, and are folded into the exported network like text prompts. Nothing is trained.
"""

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from airc.twin.config import TwinConfig
from airc.twin.twin import PartSpec, Twin
from airc.vision.camera import CameraModel
from airc.vision.render import FrameRenderer, Randomisation

ROI_PX = 640
Scene = tuple[tuple[int, float, float, float], ...]  # (class, dx from PE1, y, theta) per part
SLOTS_MM = (-150.0, 0.0, 150.0)  # part positions along the belt around PE1


def roi_slices(twin: Twin) -> tuple[slice, slice]:
    """The detector's region of interest: ``ROI_PX`` square around PE1 in the image."""
    camera = CameraModel.from_mujoco(twin.model, twin.data, "cam_inspect")
    geo = twin.geo
    z = float(np.mean([c.height_mm for c in twin.cfg.parts.classes])) / 2
    centre = np.array([geo.belt_origin_x + geo.pe1_x, geo.belt_origin_y, geo.belt_surface_z + z])
    u, v = camera.project(centre * 1e-3)
    cam = twin.cfg.camera
    u0 = int(min(max(round(u) - ROI_PX // 2, 0), cam.width_px - ROI_PX))
    v0 = int(min(max(round(v) - ROI_PX // 2, 0), cam.height_px - ROI_PX))
    return slice(v0, v0 + ROI_PX), slice(u0, u0 + ROI_PX)


def reference_scenes(seed: int, count: int, min_parts: int = 3) -> list[Scene]:
    """Seeded scenes of 1-3 parts near PE1; with ``min_parts=3`` every class appears once."""
    rng = np.random.default_rng(seed)
    scenes: list[Scene] = []
    for _ in range(count):
        if min_parts >= len(SLOTS_MM):
            classes = [int(c) for c in rng.permutation(3)]
        else:
            classes = [int(c) for c in rng.integers(0, 3, size=int(rng.integers(min_parts, 4)))]
        slots = rng.permutation(SLOTS_MM)
        scenes.append(
            tuple(
                (
                    cls,
                    float(slots[i] + rng.uniform(-30, 30)),
                    float(rng.uniform(-70, 70)),
                    float(rng.uniform(-90, 90)),
                )
                for i, cls in enumerate(classes)
            )
        )
    return scenes


def render_scene(
    scene: Scene, seed: int, cfg: TwinConfig | None = None
) -> tuple[NDArray[np.uint8], list[tuple[float, float, float, float]], list[int]]:
    """Render a scene with seeded random lighting.

    Returns the ROI image in BGR (as Ultralytics expects), the part boxes in it
    (x0, y0, x1, y1) and their classes.
    """
    twin = Twin(cfg=cfg if cfg is not None else TwinConfig.load(parts="catalogue"))
    renderer = FrameRenderer(twin.model, "cam_inspect", twin.cfg)
    try:
        pids = [
            twin.spawn(PartSpec(cls=c, y_mm=y, theta_deg=th, x_mm=twin.geo.pe1_x + dx))
            for c, dx, y, th in scene
        ]
        twin.step(twin.joint_positions_rad(), 0.0, 0.0, False)
        frame = renderer.render(twin.data, Randomisation.draw(np.random.default_rng(seed)))
    finally:
        renderer.close()
    roi = roi_slices(twin)
    bodies = frame.bodies[roi]
    boxes: list[tuple[float, float, float, float]] = []
    for pid in pids:
        vs, us = np.nonzero(bodies == twin.part_body_id(pid))
        boxes.append((float(us.min()), float(vs.min()), float(us.max()), float(vs.max())))
    bgr = np.ascontiguousarray(frame.rgb[roi][:, :, ::-1])
    return bgr, boxes, [c for c, *_ in scene]


def scene_classes(scenes: Sequence[Scene]) -> set[int]:
    """Classes that appear in the scenes."""
    return {c for scene in scenes for c, *_ in scene}
