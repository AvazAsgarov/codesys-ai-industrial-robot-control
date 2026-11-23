"""Shared pytest fixtures."""

from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def write_yaml(tmp_path: Path) -> Callable[[str], Path]:
    """Return a helper that writes YAML text to a temp file and returns its path."""

    def _write(text: str) -> Path:
        path = tmp_path / "cell.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    return _write


VALID_YAML = """\
project:
  name: codesys-ai-industrial-robot-control
  version: 0.1.0
plc:
  project_file: plc/RobotCell.project
  opcua_endpoint: opc.tcp://localhost:4840
"""
