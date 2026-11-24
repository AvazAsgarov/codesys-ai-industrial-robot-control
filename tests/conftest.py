"""Shared pytest fixtures."""

import os
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


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip `render` tests where there is no OpenGL context (CI sets AIRC_SKIP_RENDER=1)."""
    if not os.environ.get("AIRC_SKIP_RENDER"):
        return
    skip = pytest.mark.skip(reason="AIRC_SKIP_RENDER: no OpenGL context on this machine")
    for item in items:
        if "render" in item.keywords:
            item.add_marker(skip)
