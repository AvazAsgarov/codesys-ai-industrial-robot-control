import importlib.util
from pathlib import Path
from types import ModuleType

TOOL = Path(__file__).resolve().parents[2] / "tools" / "uv_run.py"


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("uv_run", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_project_env_drops_foreign_uv_environment():
    env = _load_tool().project_env({"UV_PROJECT_ENVIRONMENT": r"C:\other\venv", "PATH": "x"})
    assert "UV_PROJECT_ENVIRONMENT" not in env
    assert env["PATH"] == "x"


def test_project_env_does_not_mutate_input():
    original = {"UV_PROJECT_ENVIRONMENT": "y"}
    _load_tool().project_env(original)
    assert original == {"UV_PROJECT_ENVIRONMENT": "y"}
