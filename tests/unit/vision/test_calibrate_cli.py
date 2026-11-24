"""`airc calibrate`: writes the calibration study and the calibrated camera model."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from airc.cli import app
from airc.vision.camera import CameraModel

pytestmark = pytest.mark.render


def test_calibrate_writes_report_and_camera(tmp_path: Path) -> None:
    report = tmp_path / "calibration.json"
    model = tmp_path / "cam_inspect.json"
    result = CliRunner().invoke(
        app,
        ["calibrate", "--poses", "10", "--seed", "3", "--out", str(report), "--model", str(model)],
    )
    if "no OpenGL context" in result.output:
        pytest.skip(result.output)
    assert result.exit_code == 0, result.output
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["seed"] == 3
    assert data["views"] >= 5
    assert data["rms_px"] < 0.5
    assert abs(data["focal_error_pct"]) < 1.0
    camera = CameraModel.load(model)
    assert camera.width == 1280
    assert "position error" in result.output
