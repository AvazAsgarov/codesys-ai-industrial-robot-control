"""Twin configuration (``config/twin.yaml``)."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from airc.common.config import default_config_path

Six = tuple[float, float, float, float, float, float]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BeltConfig(_Frozen):
    """Belt dimensions (mm)."""

    length_mm: float
    width_mm: float
    thickness_mm: float


class ServoConfig(_Frozen):
    """Simulated servo drives (PD + velocity feed-forward), one entry per joint J1..J6."""

    kp: Six
    kv: Six
    friction: Six
    torque_limit: Six
    armature: Six
    range_deg: tuple[tuple[float, float], ...]


class PartClass(_Frozen):
    """A part type: box (x, y, z mm), cylinder (diameter, height mm) or scanned mesh (x, y, z mm).

    A mesh part's origin is the middle of its height at the centroid of its top view;
    ``grip_mm`` is its top surface above the belt there (where the suction cup lands).
    """

    name: str
    shape: Literal["box", "cylinder", "mesh"]
    size_mm: tuple[float, ...]
    rgba: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    mesh_file: str | None = None
    texture_file: str | None = None
    grip_mm: float | None = None

    @property
    def height_mm(self) -> float:
        """Height of the part."""
        return self.size_mm[-1]

    @property
    def grip_height_mm(self) -> float:
        """Top surface above the belt where the suction cup lands (the part's origin)."""
        return self.grip_mm if self.grip_mm is not None else self.height_mm

    @property
    def length_mm(self) -> float:
        """Extent along the belt at theta 0."""
        return self.size_mm[0]


class PartsConfig(_Frozen):
    """Part catalogue of the twin."""

    mass_kg: float
    friction: float
    pool_per_class: int
    classes: tuple[PartClass, ...]


class SuctionConfig(_Frozen):
    """Suction cup."""

    max_gap_mm: float
    cup_radius_mm: float


class CameraConfig(_Frozen):
    """Inspection camera ``cam_inspect``: image size, field of view and placement over PE1."""

    width_px: int
    height_px: int
    fovy_deg: float
    tilt_deg: float
    distance_mm: float


class BinsConfig(_Frozen):
    """Bins (inner size in mm)."""

    size_mm: tuple[float, float, float]
    wall_mm: float
    capacity: int


class TwinConfig(_Frozen):
    """Root of ``config/twin.yaml``."""

    physics_timestep_s: float
    bridge_period_s: float
    bridge_timeout_s: float  # OPC UA request timeout of the bridge cycle
    belt: BeltConfig
    photo_eye_height_mm: float
    camera: CameraConfig
    servo: ServoConfig
    parts: PartsConfig
    suction: SuctionConfig
    bins: BinsConfig

    @classmethod
    def load(
        cls,
        path: Path | None = None,
        parts: Literal["placeholder", "catalogue"] = "placeholder",
        classes: Sequence[str] | None = None,
    ) -> "TwinConfig":
        """Load ``config/twin.yaml`` (default: the repository's).

        Args:
            path: The twin configuration file.
            parts: ``placeholder`` - the geometric parts of ``twin.yaml``; ``catalogue`` - the
                three scanned parts of ``config/parts.yaml`` (Phase 3).
            classes: With ``catalogue``: these candidate slugs as the classes instead of the
                ``classes`` of ``parts.yaml`` (the benchmark compares candidates).
        """
        file = path if path is not None else default_config_path().parent / "twin.yaml"
        raw: Any = yaml.safe_load(file.read_text(encoding="utf-8"))
        cfg = cls.model_validate(raw)
        if parts == "catalogue":
            from airc.twin.catalogue import PartCatalogue  # noqa: PLC0415 - avoids a cycle

            catalogue = PartCatalogue.load(file.parent / "parts.yaml")
            if classes is not None:
                catalogue = catalogue.with_classes(classes)
            part_classes = tuple(
                PartClass(
                    name=p.slug,
                    shape="mesh",
                    size_mm=p.size_mm,
                    mesh_file=p.mesh_path.as_posix(),
                    texture_file=p.texture_path.as_posix(),
                    grip_mm=p.grip_height_mm,
                )
                for p in catalogue.classes
            )
            cfg = cfg.model_copy(
                update={"parts": cfg.parts.model_copy(update={"classes": part_classes})}
            )
        return cfg

    def with_camera_tilt(self, tilt_deg: float) -> "TwinConfig":
        """The same configuration with another inspection camera tilt (benchmark studies)."""
        return self.model_copy(
            update={"camera": self.camera.model_copy(update={"tilt_deg": tilt_deg})}
        )
