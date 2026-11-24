"""Soft-PLC process handling: PID reuse, stale deploy logs, network exposure (review fixes)."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from airc.plc import runtime


class _Calls:
    """Records subprocess.run calls and answers ``tasklist`` with a fixed CSV line."""

    def __init__(self, tasklist_out: str) -> None:
        self.tasklist_out = tasklist_out
        self.commands: list[object] = []

    def __call__(self, cmd: object, *args: object, **kwargs: object) -> SimpleNamespace:
        self.commands.append(cmd)
        out = self.tasklist_out if isinstance(cmd, list) and cmd[0] == "tasklist" else ""
        return SimpleNamespace(stdout=out, returncode=0)

    def ran(self, program: str) -> bool:
        return any(isinstance(c, list) and c[0] == program for c in self.commands)


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(runtime, "_state_dir", lambda: tmp_path)
    return tmp_path


def test_stop_does_not_kill_a_reused_pid(state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (state_dir / "runtime.pid").write_text("1234", encoding="utf-8")
    calls = _Calls('"WINWORD.EXE","1234","Console","1","250,000 K"\n')
    monkeypatch.setattr(runtime.subprocess, "run", calls)
    assert runtime.stop() is False
    assert not calls.ran("taskkill")


def test_stop_kills_the_runtime_it_started(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (state_dir / "runtime.pid").write_text("1234", encoding="utf-8")
    calls = _Calls('"CODESYSControlService.exe","1234","Console","1","90,000 K"\n')
    monkeypatch.setattr(runtime.subprocess, "run", calls)
    assert runtime.stop() is True
    assert calls.ran("taskkill")


SETTINGS = runtime.load_runtime_settings()  # from the real repository, before any patching


@pytest.fixture
def deploy_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "plc" / "scripts").mkdir(parents=True)
    (tmp_path / "RobotCell.project").write_bytes(b"project")
    monkeypatch.setattr(runtime, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        runtime, "read_dotenv", lambda _p: {"AIRC_PLC_USER": "u", "AIRC_PLC_PASSWORD": "p"}
    )
    return tmp_path


def test_deploy_ignores_a_stale_log(deploy_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = deploy_root / "plc" / "scripts" / "deploy_runtime.log"
    log.write_text(f"old run\n{runtime.DEPLOY_OK}\n", encoding="utf-8")
    monkeypatch.setattr(runtime.subprocess, "run", _Calls(""))  # the IDE never ran the script
    with pytest.raises(RuntimeError, match="deploy failed"):
        runtime.deploy(SETTINGS, deploy_root / "RobotCell.project")


def test_deploy_timeout_is_a_runtime_error(
    deploy_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def hang(cmd: str, *args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd, 1.0)

    monkeypatch.setattr(runtime.subprocess, "run", hang)
    with pytest.raises(RuntimeError, match="did not finish"):
        runtime.deploy(SETTINGS, deploy_root / "RobotCell.project")


def test_start_refuses_when_the_firewall_allows_inbound(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def must_not_launch(_settings: object) -> int:
        raise AssertionError("the runtime must not be started")

    monkeypatch.setattr(runtime, "firewall_allows_inbound", lambda _exe: True)
    monkeypatch.setattr(runtime, "_launch", must_not_launch)
    with pytest.raises(RuntimeError, match="firewall"):
        runtime.start(runtime.load_runtime_settings())


def test_firewall_check_expands_environment_variables() -> None:
    script = runtime.firewall_script(Path(r"C:\Program Files\CODESYS\x.exe"))
    assert "ExpandEnvironmentVariables" in script


def test_ide_processes_found_and_exempted(monkeypatch: pytest.MonkeyPatch) -> None:
    # CODESYS's own simulation runs inside the (windowless) IDE: throttled, it ran at ~27 % speed
    calls = _Calls(
        '"CODESYS.exe","18164","Console","1","1,000,000 K"\n'
        '"CODESYS.exe","2280","Console","1","300,000 K"\n'
    )
    monkeypatch.setattr(runtime.subprocess, "run", calls)
    exempted: list[int] = []
    monkeypatch.setattr(
        runtime, "disable_timer_throttling", lambda pid: exempted.append(pid) or True
    )
    assert runtime.unthrottle_ide() == [18164, 2280]
    assert exempted == [18164, 2280]
