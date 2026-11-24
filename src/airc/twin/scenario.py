"""Seeded scenarios: which parts appear on the belt, and when (``config/scenarios/*.yaml``).

Parts are spawned by belt travel, not by wall time: a new part appears every ``pitch_mm`` of belt
movement (± jitter), so spawning pauses whenever the PLC stops the belt and the spacing on the
belt never depends on the PLC's speed or on the simulator's pace.
"""

from pathlib import Path
from typing import Any

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field

from airc.twin.twin import PartSpec


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SpawnConfig(_Frozen):
    """Part supply at the belt infeed."""

    pitch_mm: float = Field(gt=0)
    jitter_mm: float = Field(default=0.0, ge=0)
    mix: tuple[float, ...] = (1.0, 1.0, 1.0)  # relative weights per class
    y_offset_mm: float = 0.0  # uniform in +/- this
    theta_deg: float = 0.0  # uniform in +/- this


class Scenario(_Frozen):
    """A run of the cell: seed, part supply and (later) faults."""

    name: str
    seed: int
    duration_s: float | None = None
    spawn: SpawnConfig
    bin_capacity: int | None = None

    @classmethod
    def load(cls, path: Path) -> "Scenario":
        """Load a scenario YAML file."""
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.model_validate(raw)


class SpawnSchedule:
    """Deterministic part supply for a scenario (same seed, same parts)."""

    def __init__(self, scenario: Scenario) -> None:
        """Start the schedule at belt position 0."""
        self._cfg = scenario.spawn
        self._rng = np.random.default_rng(scenario.seed)
        weights = np.array(self._cfg.mix, dtype=np.float64)
        self._p = weights / weights.sum()
        self._next_mm: float | None = None

    def _draw_pitch(self) -> float:
        jitter = self._cfg.jitter_mm
        return self._cfg.pitch_mm + float(self._rng.uniform(-jitter, jitter))

    def _draw_part(self) -> PartSpec:
        cls = int(self._rng.choice(len(self._p), p=self._p))
        y = float(self._rng.uniform(-self._cfg.y_offset_mm, self._cfg.y_offset_mm))
        theta = float(self._rng.uniform(-self._cfg.theta_deg, self._cfg.theta_deg))
        return PartSpec(cls=cls, y_mm=y, theta_deg=theta)

    def due(self, belt_pos_mm: float) -> list[PartSpec]:
        """Parts to spawn now, given the conveyor position (mm)."""
        if self._next_mm is None:  # first part as soon as the belt has moved a little
            self._next_mm = belt_pos_mm + 1.0
        parts: list[PartSpec] = []
        while belt_pos_mm >= self._next_mm:
            parts.append(self._draw_part())
            self._next_mm += self._draw_pitch()
        return parts
