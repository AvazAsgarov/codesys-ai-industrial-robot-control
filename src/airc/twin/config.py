"""Twin configuration (``config/twin.yaml``)."""

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
    """Simulated servo drives, one entry per joint J1..J6."""

    kp: Six
    damping: Six
    torque_limit: Six
    armature: Six
    range_deg: tuple[tuple[float, float], ...]


class PartClass(_Frozen):
    """A part type: box (x, y, z mm) or cylinder (diameter, height mm)."""

    name: str
    shape: Literal["box", "cylinder"]
    size_mm: tuple[float, ...]
    rgba: tuple[float, float, float, float]

    @property
    def height_mm(self) -> float:
        """Height of the part."""
        return self.size_mm[-1]

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


class BinsConfig(_Frozen):
    """Bins (inner size in mm)."""

    size_mm: tuple[float, float, float]
    wall_mm: float
    capacity: int


class TwinConfig(_Frozen):
    """Root of ``config/twin.yaml``."""

    physics_timestep_s: float
    bridge_period_s: float
    belt: BeltConfig
    photo_eye_height_mm: float
    servo: ServoConfig
    parts: PartsConfig
    suction: SuctionConfig
    bins: BinsConfig

    @classmethod
    def load(cls, path: Path | None = None) -> "TwinConfig":
        """Load ``config/twin.yaml`` (default: the repository's)."""
        file = path if path is not None else default_config_path().parent / "twin.yaml"
        raw: Any = yaml.safe_load(file.read_text(encoding="utf-8"))
        return cls.model_validate(raw)
