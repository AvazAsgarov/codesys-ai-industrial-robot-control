"""Scanned part catalogue (config/parts.yaml + assets/objects): fit, rest, grip, size on disk."""

import re
from pathlib import Path

import numpy as np
import pytest

from airc.twin.catalogue import PartCatalogue
from airc.twin.config import TwinConfig
from airc.twin.twin import PartSpec, Twin

REPO = Path(__file__).resolve().parents[3]
HOME_RAD = np.radians([0.0, -30.0, 60.0, 0.0, 60.0, 0.0])
MAX_FOOTPRINT_MM = 120.0  # bins are 160 mm wide; a carried part must clear the walls


@pytest.fixture(scope="module")
def catalogue() -> PartCatalogue:
    return PartCatalogue.load()


@pytest.fixture(scope="module")
def twin() -> Twin:
    return Twin(cfg=TwinConfig.load(parts="catalogue"))


def test_catalogue_parts_fit_the_cell(catalogue: PartCatalogue) -> None:
    assert len(catalogue.classes) == 3
    for part in catalogue.candidates:
        x, y, z = part.size_mm
        assert max(x, y) <= MAX_FOOTPRINT_MM, part.slug
        assert 30.0 <= z <= 90.0, part.slug
        assert part.prompt
        assert 0.3 * z <= part.grip_height_mm <= z + 0.01, part.slug


def test_mesh_files_small(catalogue: PartCatalogue) -> None:
    for part in catalogue.candidates:
        size = part.mesh_path.stat().st_size + part.texture_path.stat().st_size
        assert size <= 3_000_000, f"{part.slug}: {size} bytes"
        assert (part.mesh_path.parent / "LICENSE.txt").is_file()


@pytest.mark.parametrize("cls", [0, 1, 2])
def test_mesh_part_rests_on_belt(twin: Twin, cls: int) -> None:
    pid = twin.spawn(PartSpec(cls=cls, y_mm=0.0, theta_deg=20.0, x_mm=300.0 + 500.0 * cls))
    for _ in range(50):  # 1 s
        twin.step(HOME_RAD, 0.0, 0.0, False)
    part = twin.part(pid)
    height = twin.cfg.parts.classes[cls].height_mm
    assert part.on_belt
    assert part.z_mm == pytest.approx(twin.geo.belt_surface_z + height / 2, abs=2.0)
    assert abs(part.theta_deg - 20.0) < 2.0  # it did not topple or spin
    twin.drop_part(block_grip=False)


@pytest.mark.parametrize("cls", [0, 1, 2])
def test_mesh_part_grippable_at_its_grip_height(cls: int) -> None:
    twin = Twin(cfg=TwinConfig.load(parts="catalogue"))
    pid = twin.spawn(PartSpec(cls=cls, y_mm=0.0, theta_deg=0.0, x_mm=900.0))
    twin.step(HOME_RAD, 0.0, 0.0, False)
    twin.place_part_under_cup(pid, gap_mm=10.0)
    assert not twin.step(twin.joint_positions_rad(), 0.0, 0.0, True).vacuum_ok
    twin.place_part_under_cup(pid, gap_mm=3.0)
    assert twin.step(twin.joint_positions_rad(), 0.0, 0.0, True).vacuum_ok


@pytest.mark.xfail(reason="PLC per-class pick heights come in plan Task 6", strict=True)
def test_plc_part_heights_match_catalogue(catalogue: PartCatalogue) -> None:
    text = (REPO / "plc/src/Config/GVL_CellGeometry.st").read_text(encoding="utf-8")
    match = re.search(r"PART_HEIGHTS\s*:\s*ARRAY\[0\.\.2\] OF LREAL\s*:=\s*\[([^\]]*)\]", text)
    assert match, "GVL_CellGeometry.PART_HEIGHTS is missing"
    plc = [float(v) for v in match.group(1).split(",")]
    assert plc == pytest.approx([p.grip_height_mm for p in catalogue.classes], abs=0.5)


def test_unprepared_candidate_is_skipped_but_a_class_is_required(tmp_path: Path) -> None:
    src = REPO / "assets" / "objects"
    cfg = tmp_path / "config"
    cfg.mkdir()
    text = (REPO / "config" / "parts.yaml").read_text(encoding="utf-8")
    (cfg / "parts.yaml").write_text(text, encoding="utf-8")
    assets = tmp_path / "assets" / "objects"
    chosen = PartCatalogue.load().classes
    for part in chosen:  # only the three classes are prepared
        (assets / part.slug).mkdir(parents=True)
        for name in ("meta.json", "model.obj", "texture.png"):
            (assets / part.slug / name).write_bytes((src / part.slug / name).read_bytes())
    cat = PartCatalogue.load(cfg / "parts.yaml", assets)
    assert [p.slug for p in cat.candidates] == [p.slug for p in chosen]
    (assets / chosen[0].slug / "meta.json").unlink()
    with pytest.raises(FileNotFoundError, match="fetch_objects"):
        PartCatalogue.load(cfg / "parts.yaml", assets)
