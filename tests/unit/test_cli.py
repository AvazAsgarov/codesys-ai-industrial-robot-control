from typer.testing import CliRunner

import airc
from airc.cli import app
from tests.conftest import VALID_YAML

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"airc {airc.__version__}" in result.output


def test_cli_config_show():
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "opc.tcp://127.0.0.1:4840" in result.output


def test_cli_bad_config_exit_code(write_yaml):
    bad = write_yaml(VALID_YAML.replace("opcua_endpoint:", "opcua_endpointt:"))
    result = runner.invoke(app, ["config", "show", "--config", str(bad)])
    assert result.exit_code == 2
    assert "opcua_endpointt" in result.output
    assert "Traceback" not in result.output


def test_cli_run_rejects_an_unknown_record_camera(tmp_path):
    out = tmp_path / "demo.mp4"
    args = ["run", "--record", str(out), "--record-camera", "no_such_cam", "--duration", "1"]
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert "no_such_cam" in result.output
    assert not out.exists()
