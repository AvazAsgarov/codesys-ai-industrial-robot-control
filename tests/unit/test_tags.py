"""The OPC UA tag map (config/opcua_tags.yaml) against the PLC sources."""

import re
from pathlib import Path

import pytest

from airc.bridge.tags import TagMap

REPO = Path(__file__).resolve().parents[2]
GVL_BRIDGE = REPO / "plc" / "src" / "Comm" / "GVL_Bridge.st"


def _gvl_variables(path: Path) -> list[str]:
    names: list[str] = []
    in_block = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("//", 1)[0].strip()
        if line.startswith("VAR_GLOBAL"):
            in_block = True
        elif line.startswith("END_VAR"):
            in_block = False
        elif in_block and (m := re.match(r"(\w+)\s*:", line)):
            names.append(m.group(1))
    return names


def test_tag_map_has_every_gvl_bridge_var() -> None:
    tags = TagMap.load()
    paths = {tag.path for tag in tags.tags.values()}
    variables = _gvl_variables(GVL_BRIDGE)
    assert "xTwinActive" in variables
    for var in variables:
        full = f"GVL_Bridge.{var}"
        assert any(p == full or p.startswith(full + ".") for p in paths), full


def test_node_id_uses_the_codesys_prefix() -> None:
    tags = TagMap.load()
    assert tags.node_id("state") == (
        "ns=4;s=|var|CODESYS Control Win V3 x64.Application.GVL_Bridge.eState"
    )
    assert tags.tags["vision.seq"].path == "GVL_Bridge.stVision.udiSeq"
    assert tags.tags["joint_fb_deg"].variant == "Double"


def test_unknown_tag_raises() -> None:
    with pytest.raises(KeyError, match="no_such_tag"):
        TagMap.load().node_id("no_such_tag")
