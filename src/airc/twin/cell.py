"""Cell geometry for the twin, read from the PLC sources (``GVL_CellGeometry.st``).

The PLC is the single source of the cell's geometry: robot kinematics, belt frame, photo-eye
positions and bin drop poses. Units here are the PLC's (mm, degrees, robot base frame).
"""

import re
from dataclasses import dataclass
from pathlib import Path

from airc.common.config import default_config_path

_SCALAR = re.compile(r"^\s*(\w+)\s*:\s*LREAL\s*:=\s*(-?[\d.]+)\s*;", re.MULTILINE)
_COORD_FIELD = re.compile(r"(\w)\s*:=\s*(-?[\d.]+)")


def _coords(text: str) -> dict[str, float]:
    return {k: float(v) for k, v in _COORD_FIELD.findall(text)}


@dataclass(frozen=True)
class CellGeometry:
    """Geometry constants of the cell (mm)."""

    robot_a1: float
    robot_d1: float
    robot_a2: float
    robot_a3: float
    robot_d3: float
    robot_d4: float
    robot_d6: float
    belt_origin_x: float
    belt_origin_y: float
    belt_surface_z: float
    pe1_x: float
    pe2_x: float
    pick_window_end_x: float
    part_height: float
    bin_drop_xy: tuple[tuple[float, float], ...]

    @classmethod
    def from_plc_sources(cls, path: Path | None = None) -> "CellGeometry":
        """Parse ``plc/src/Config/GVL_CellGeometry.st``."""
        root = default_config_path().resolve().parent.parent
        file = path if path is not None else root / "plc/src/Config/GVL_CellGeometry.st"
        text = file.read_text(encoding="utf-8")
        scalars = {name: float(value) for name, value in _SCALAR.findall(text)}
        origin_match = re.search(r"BELT_ORIGIN\s*:\s*MC_COORD_REF\s*:=\s*\(([^)]*)\)", text)
        bins_match = re.search(r"BIN_DROP\s*:.*?:=\s*\[(.*?)\];", text, re.DOTALL)
        if origin_match is None or bins_match is None:
            msg = f"BELT_ORIGIN or BIN_DROP not found in {file}"
            raise ValueError(msg)
        origin = _coords(origin_match.group(1))
        bins = tuple(
            (c["X"], c["Y"])
            for c in (_coords(b) for b in re.findall(r"\(([^)]*)\)", bins_match.group(1)))
        )
        return cls(
            robot_a1=scalars["ROBOT_A1"],
            robot_d1=scalars["ROBOT_D1"],
            robot_a2=scalars["ROBOT_A2"],
            robot_a3=scalars["ROBOT_A3"],
            robot_d3=scalars["ROBOT_D3"],
            robot_d4=scalars["ROBOT_D4"],
            robot_d6=scalars["ROBOT_D6"],
            belt_origin_x=origin["X"],
            belt_origin_y=origin["Y"],
            belt_surface_z=scalars["BELT_SURFACE_Z"],
            pe1_x=scalars["PE1_X"],
            pe2_x=scalars["PE2_X"],
            pick_window_end_x=scalars["PICK_WINDOW_END_X"],
            part_height=scalars["PART_HEIGHT"],
            bin_drop_xy=bins,
        )
