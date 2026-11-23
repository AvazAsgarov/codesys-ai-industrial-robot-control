"""Validate the PLC simulation test specs in tests/plc/*.json.

The specs are executed against CODESYS's simulation (``codesys_sim_test``), which CI cannot run.
CI still guarantees that every spec file is well formed.
"""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[2] / "tests" / "plc"
ALLOWED_STEP_KEYS = {"write", "force", "unforce", "cycles", "waitMs", "expect"}
SPEC_FILES = sorted(SPEC_DIR.glob("*.json"))


def test_plc_specs_exist():
    assert SPEC_FILES, f"no PLC test specs in {SPEC_DIR}"


@pytest.mark.parametrize("spec_file", SPEC_FILES, ids=lambda p: p.name)
def test_every_plc_spec_is_well_formed(spec_file: Path):
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    cases = spec["cases"]
    assert isinstance(cases, list)
    assert cases, "spec has no cases"
    names = [case["name"] for case in cases]
    assert len(names) == len(set(names)), "duplicate case names"
    for case in cases:
        assert case["steps"], f"case {case['name']} has no steps"
        for step in case["steps"]:
            assert step, f"empty step in {case['name']}"
            unknown = set(step) - ALLOWED_STEP_KEYS
            assert not unknown, f"unknown step keys {unknown} in {case['name']}"
        assert any("expect" in step for step in case["steps"]), (
            f"case {case['name']} asserts nothing"
        )
