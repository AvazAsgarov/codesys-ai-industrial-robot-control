"""Labelled benchmark frames rendered from the digital twin (plan Task 7).

Each frame puts one to three parts of the chosen classes on the belt near photo-eye PE1, as the
spawner does (x within +-150 mm of PE1, y within +-80 mm, any orientation, no overlap), renders
the inspection camera with a seeded image randomisation and crops the same region of interest
around PE1 that the vision worker gives the detector. The ground truth of every visible part is
exact: its mask and box from the segmentation render and its pose from the simulator.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from airc.twin.catalogue import PartCatalogue
from airc.twin.cell import CellGeometry
from airc.twin.config import PartClass, TwinConfig
from airc.twin.twin import PartSpec, Twin
from airc.vision.camera import CameraModel
from airc.vision.render import FrameRenderer, Randomisation
from airc.vision.service import Roi, crop_roi, pe1_roi

X_RANGE_MM = 150.0  # part centre: PE1 +- this along the belt
Y_RANGE_MM = 80.0  # and +- this across it
MAX_PARTS = 3
PLACEMENT_TRIES = 50  # a part that does not fit without overlap after this many draws is dropped
GAP_MM = 5.0  # minimum clearance between the footprint circles of two parts
MIN_VISIBLE_PX = 200  # a part showing fewer pixels in the window is not labelled


@dataclass(frozen=True)
class SceneInfo:
    """What every frame of a dataset shares: classes, camera and the window."""

    slugs: tuple[str, ...]  # class index -> candidate slug
    prompts: tuple[str, ...]  # YOLOE text prompt per class
    coco: tuple[str | None, ...]  # COCO name per class (YOLO26 baseline)
    symmetry: tuple[int, ...]  # rotational symmetry per class (0 = round)
    classes: tuple[PartClass, ...]  # size per class (as the vision worker uses it)
    tilt_deg: float
    camera: CameraModel  # pixel -> belt conversion (the exact camera unless given another)
    geo: CellGeometry
    roi: Roi  # the window in the full camera image


@dataclass(frozen=True)
class PartLabel:
    """Ground truth of one visible part (pixels in the window, pose in the belt frame)."""

    cls: int
    body_id: int
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 (x1, y1 exclusive) of the mask
    mask: NDArray[np.bool_]
    x_mm: float
    y_mm: float
    theta_deg: float


@dataclass(frozen=True)
class LabelledFrame:
    """The detector's input image and the truth of the parts in it."""

    index: int
    rgb: NDArray[np.uint8]
    bodies: NDArray[np.int32]  # MuJoCo body id per pixel (-1 background)
    parts: tuple[PartLabel, ...]
    scene: SceneInfo


def _with_classes(cfg: TwinConfig, slugs: Sequence[str] | None) -> TwinConfig:
    if slugs is None:
        return cfg
    return cfg.model_copy(update={"parts": TwinConfig.load(parts="catalogue", classes=slugs).parts})


def _draw_parts(
    rng: np.random.Generator, cfg: TwinConfig, pe1_x: float
) -> list[tuple[int, float, float, float]]:
    """1-3 non-overlapping parts (class, x, y, theta), uniform over the classes."""
    radii = [float(np.hypot(c.size_mm[0], c.size_mm[1])) / 2 for c in cfg.parts.classes]
    placed: list[tuple[int, float, float, float]] = []
    for _ in range(int(rng.integers(1, MAX_PARTS + 1))):
        cls = int(rng.integers(len(radii)))
        for _ in range(PLACEMENT_TRIES):
            x = pe1_x + float(rng.uniform(-X_RANGE_MM, X_RANGE_MM))
            y = float(rng.uniform(-Y_RANGE_MM, Y_RANGE_MM))
            if all(
                np.hypot(x - px, y - py) >= radii[cls] + radii[pc] + GAP_MM
                for pc, px, py, _ in placed
            ):
                placed.append((cls, x, y, float(rng.uniform(-180.0, 180.0))))
                break
    return placed


def render_dataset(
    seed: int,
    frames: int,
    twin_cfg: TwinConfig,
    part_slugs: Sequence[str] | None = None,
    camera: CameraModel | None = None,
) -> Iterator[LabelledFrame]:
    """Render ``frames`` labelled frames; the same seed and configuration give the same frames.

    Args:
        seed: Seed of the part placement and the image randomisation.
        frames: Number of frames.
        twin_cfg: Twin configuration (its camera block sets the tilt); its parts must be
            catalogue parts unless ``part_slugs`` is given.
        part_slugs: Catalogue candidates to use as the classes (default: ``twin_cfg``'s).
        camera: Camera model for the window and pixel -> belt (default: the exact camera).

    Yields:
        One labelled frame after another (the renderer lives as long as the iterator).
    """
    cfg = _with_classes(twin_cfg, part_slugs)
    slugs = [c.name for c in cfg.parts.classes]
    catalogue = PartCatalogue.load().with_classes(slugs)
    twin = Twin(cfg=cfg)
    cam = (
        camera
        if camera is not None
        else CameraModel.from_mujoco(twin.model, twin.data, "cam_inspect")
    )
    roi = pe1_roi(cam, twin.geo, cfg)
    scene = SceneInfo(
        slugs=tuple(slugs),
        prompts=tuple(p.prompt for p in catalogue.classes),
        coco=tuple(p.coco for p in catalogue.classes),
        symmetry=tuple(p.symmetry for p in catalogue.classes),
        classes=cfg.parts.classes,
        tilt_deg=cfg.camera.tilt_deg,
        camera=cam,
        geo=twin.geo,
        roi=roi,
    )
    rng = np.random.default_rng(seed)
    renderer = FrameRenderer(twin.model, "cam_inspect", cfg)
    try:
        for index in range(frames):
            pids = [
                twin.spawn(PartSpec(cls=cls, y_mm=y, theta_deg=theta, x_mm=x))
                for cls, x, y, theta in _draw_parts(rng, cfg, twin.geo.pe1_x)
            ]
            window = crop_roi(renderer.render(twin.data, Randomisation.draw(rng)), roi)
            labels: list[PartLabel] = []
            for pid in pids:
                truth = twin.part(pid)
                body = twin.part_body_id(pid)
                mask = window.bodies == body
                if int(mask.sum()) < MIN_VISIBLE_PX:
                    continue
                vs, us = np.nonzero(mask)
                labels.append(
                    PartLabel(
                        cls=truth.cls,
                        body_id=body,
                        box=(int(us.min()), int(vs.min()), int(us.max()) + 1, int(vs.max()) + 1),
                        mask=mask,
                        x_mm=truth.x_mm,
                        y_mm=truth.y_mm,
                        theta_deg=truth.theta_deg,
                    )
                )
            for pid in pids:
                twin.remove_part(pid)
            yield LabelledFrame(index, window.rgb, window.bodies, tuple(labels), scene)
    finally:
        renderer.close()
