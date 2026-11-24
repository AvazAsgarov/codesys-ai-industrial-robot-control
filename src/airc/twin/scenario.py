"""Seeded scenarios: which parts appear on the belt, when, and which faults happen.

Scenario files live in ``config/scenarios/*.yaml``.

Parts are spawned by belt travel, not by wall time: a new part appears every ``pitch_mm`` of belt
movement (± jitter), so spawning pauses whenever the PLC stops the belt and the spacing on the
belt never depends on the PLC's speed or on the simulator's pace.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from airc.twin.twin import BELT_JUMP_M, PartSpec


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SpawnConfig(_Frozen):
    """Part supply at the belt infeed."""

    pitch_mm: float = Field(gt=0)
    jitter_mm: float = Field(default=0.0, ge=0)
    mix: tuple[float, ...] = (1.0, 1.0, 1.0)  # relative weights per class
    y_offset_mm: float = 0.0  # uniform in +/- this
    theta_deg: float = 0.0  # uniform in +/- this


FaultKind = Literal["estop", "door_open", "drop_part", "block_bin", "lose_bridge", "block_joint"]
_TARGETED = ("block_bin", "block_joint")
_EPS = 1e-9


class Fault(_Frozen):
    """A fault injected at ``at_s`` seconds into the run, active for ``duration_s``.

    Kinds: ``estop`` (E-stop circuit opens), ``door_open`` (safety door opens), ``drop_part``
    (the gripped part falls; suction cannot grip again while active), ``block_bin`` (bin
    ``target`` 0..5 reports full), ``lose_bridge`` (the bridge stops talking to the PLC),
    ``block_joint`` (joint ``target`` 0..5 cannot move).
    """

    at_s: float = Field(ge=0)
    kind: FaultKind
    duration_s: float = Field(default=0.0, ge=0)
    target: int | None = Field(default=None, ge=0, le=5)

    @model_validator(mode="after")
    def _target_given(self) -> Self:
        if self.kind in _TARGETED and self.target is None:
            msg = f"fault {self.kind} needs a target (0..5)"
            raise ValueError(msg)
        return self


class Scenario(_Frozen):
    """A run of the cell: seed, part supply and faults."""

    name: str
    seed: int
    duration_s: float | None = None
    spawn: SpawnConfig
    bin_capacity: int | None = None
    parts: Literal["placeholder", "catalogue"] = "catalogue"  # scanned parts since Phase 3
    faults: tuple[Fault, ...] = ()

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
        self._next_mm: float | None = None  # belt travel at which the next part is due
        self._travel_mm = 0.0
        self._last_pos_mm: float | None = None

    def _draw_pitch(self) -> float:
        jitter = self._cfg.jitter_mm
        return self._cfg.pitch_mm + float(self._rng.uniform(-jitter, jitter))

    def _draw_part(self) -> PartSpec:
        cls = int(self._rng.choice(len(self._p), p=self._p))
        y = float(self._rng.uniform(-self._cfg.y_offset_mm, self._cfg.y_offset_mm))
        theta = float(self._rng.uniform(-self._cfg.theta_deg, self._cfg.theta_deg))
        return PartSpec(cls=cls, y_mm=y, theta_deg=theta)

    def due(self, belt_pos_mm: float) -> list[PartSpec]:
        """Parts to spawn now, given the conveyor position (mm).

        Spacing follows belt *travel*: a jump of the position (PLC restart or re-download sets it
        back to 0) is not travel, as in :meth:`Twin.step`.
        """
        if self._last_pos_mm is not None:
            delta = belt_pos_mm - self._last_pos_mm
            if abs(delta) <= BELT_JUMP_M * 1000.0:
                self._travel_mm += delta
        self._last_pos_mm = belt_pos_mm
        if self._next_mm is None:  # first part as soon as the belt has moved a little
            self._next_mm = self._travel_mm + 1.0
        parts: list[PartSpec] = []
        while self._travel_mm >= self._next_mm:
            parts.append(self._draw_part())
            self._next_mm += self._draw_pitch()
        return parts


@dataclass(frozen=True)
class FaultEvent:
    """A fault starting (``start``) or ending."""

    fault: Fault
    start: bool


class FaultTimeline:
    """Reports each fault's start and end exactly once, as run time passes."""

    def __init__(self, scenario: Scenario) -> None:
        """Prepare the scenario's faults."""
        self._faults = scenario.faults
        self._started = [False] * len(self._faults)
        self._ended = [False] * len(self._faults)

    def events(self, t_s: float) -> list[FaultEvent]:
        """Fault starts and ends due at run time ``t_s`` (seconds), in scenario order."""
        out: list[FaultEvent] = []
        for i, fault in enumerate(self._faults):
            if not self._started[i] and t_s + _EPS >= fault.at_s:
                self._started[i] = True
                out.append(FaultEvent(fault, start=True))
            due_end = t_s + _EPS >= fault.at_s + fault.duration_s
            if self._started[i] and not self._ended[i] and due_end:
                self._ended[i] = True
                out.append(FaultEvent(fault, start=False))
        return out
