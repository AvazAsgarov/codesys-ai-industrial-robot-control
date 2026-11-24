"""CODESYS Control Win V3 x64 as the project's soft-PLC (ADR 0008).

The runtime is started as a console process of the current user (``CODESYSControlService.exe -d``),
so no administrator rights are needed. Its data and configuration live under
``%APPDATA%/CODESYS/CODESYSControlWinV3x64/<instance id>/``. Before every start the settings of
``config/runtime.yaml`` are applied to that ``CODESYSControl.cfg``.

The PLC application is deployed headlessly by the CODESYS IDE running the IronPython script
``plc/scripts/deploy_runtime.py`` on a temporary copy of ``plc/RobotCell.project``.
"""

import asyncio
import ctypes
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from asyncua import ua
from asyncua.client.client import Client
from pydantic import BaseModel, ConfigDict, field_validator

from airc.common.config import ConfigError, default_config_path

CFG_NAME = "CODESYSControl.cfg"
DEPLOY_OK = "DEPLOY OK"
_CREATE_NO_WINDOW = 0x08000000
_DETACHED_PROCESS = 0x00000008


class RuntimeSettings(BaseModel):
    """Soft-PLC runtime settings (``config/runtime.yaml``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    executable: Path
    data_dir: Path
    ide_executable: Path = Path("CODESYS.exe")
    ide_profile: str = ""
    gateway_port: int = 1217
    programming_port: int = 11740
    opcua_port: int = 4840
    start_timeout_s: float = 30.0
    deploy_timeout_s: float = 900.0
    settings: dict[str, dict[str, str]] = {}

    @field_validator("data_dir", "executable", "ide_executable", mode="before")
    @classmethod
    def _expand_vars(cls, value: object) -> object:
        return os.path.expandvars(value) if isinstance(value, str) else value


def repo_root() -> Path:
    """Return the repository root (the folder that holds ``config/``)."""
    return default_config_path().resolve().parent.parent


def load_runtime_settings(path: Path | None = None) -> RuntimeSettings:
    """Load ``config/runtime.yaml``.

    Args:
        path: File to load; defaults to ``config/runtime.yaml`` of the repository.

    Returns:
        The validated settings.

    Raises:
        ConfigError: If the file is missing or invalid.
    """
    cfg_path = path if path is not None else repo_root() / "config" / "runtime.yaml"
    if not cfg_path.is_file():
        msg = f"runtime configuration not found: {cfg_path}"
        raise ConfigError(msg)
    raw: Any = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return RuntimeSettings.model_validate(raw)


def _section_name(line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped[1:-1]
    return None


def apply_runtime_settings(cfg_path: Path, settings: RuntimeSettings) -> bool:
    """Write ``settings.settings`` into a ``CODESYSControl.cfg``, keeping everything else.

    A key that exists (uncommented) in its section gets the new value; a missing key is inserted
    right after its section header; a missing section is appended. Comment lines stay untouched.
    The first time the file changes, the original is saved as ``<name>.orig``.

    Args:
        cfg_path: The runtime configuration file.
        settings: Settings whose ``settings`` mapping (section -> key -> value) is applied.

    Returns:
        True if the file changed.
    """
    original = cfg_path.read_bytes().decode("utf-8", errors="surrogateescape")
    newline = "\r\n" if "\r\n" in original else "\n"
    lines = original.splitlines()
    for section, values in settings.settings.items():
        for key, value in values.items():
            _set_key(lines, section, key, value)
    updated = newline.join(lines) + newline
    if updated == original:
        return False
    backup = cfg_path.with_name(cfg_path.name + ".orig")
    if not backup.exists():
        backup.write_bytes(original.encode("utf-8", errors="surrogateescape"))
    cfg_path.write_bytes(updated.encode("utf-8", errors="surrogateescape"))
    return True


def _set_key(lines: list[str], section: str, key: str, value: str) -> None:
    entry = f"{key}={value}"
    header = next((i for i, ln in enumerate(lines) if _section_name(ln) == section), None)
    if header is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"[{section}]", entry])
        return
    end = next(
        (i for i in range(header + 1, len(lines)) if _section_name(lines[i]) is not None),
        len(lines),
    )
    for i in range(header + 1, end):
        if lines[i].split("=", 1)[0].strip() == key and not lines[i].lstrip().startswith(";"):
            lines[i] = entry
            return
    lines.insert(header + 1, entry)


@dataclass(frozen=True)
class RuntimeStatus:
    """What ``airc plc status`` reports."""

    pid: int | None
    process_alive: bool
    programming_port_open: bool
    opcua_port_open: bool
    packml_state: int | None = None
    main_task_period_ms: float | None = None


def _state_dir() -> Path:
    path = repo_root() / ".airc"
    path.mkdir(exist_ok=True)
    return path


def _pid_file() -> Path:
    return _state_dir() / "runtime.pid"


def find_runtime_cfg(settings: RuntimeSettings) -> Path | None:
    """Return the runtime's ``CODESYSControl.cfg`` (newest instance), or None before first start."""
    candidates = sorted(
        settings.data_dir.glob(f"*/{CFG_NAME}"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def port_open(port: int, host: str = "127.0.0.1", timeout_s: float = 0.5) -> bool:
    """Return True if a TCP connection to ``host:port`` succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def process_alive(pid: int) -> bool:
    """Return True if a process with this id runs (Windows ``tasklist``; never signals it)."""
    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return f'"{pid}"' in out


def _read_pid() -> int | None:
    path = _pid_file()
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return int(text) if text.isdigit() else None


_PROCESS_SET_INFORMATION = 0x0200
_PROCESS_POWER_THROTTLING = 4  # PROCESS_INFORMATION_CLASS.ProcessPowerThrottling
_THROTTLING_VERSION = 1
_THROTTLING_EXECUTION_SPEED = 0x1
_THROTTLING_IGNORE_TIMER_RESOLUTION = 0x4


class _PowerThrottlingState(ctypes.Structure):
    _fields_ = (
        ("Version", wintypes.ULONG),
        ("ControlMask", wintypes.ULONG),
        ("StateMask", wintypes.ULONG),
    )


def disable_timer_throttling(pid: int) -> bool:
    """Exempt a process from Windows 11 power throttling of timers and execution speed.

    Windows 11 ignores the timer-resolution request of a process without a visible window, so
    the soft-PLC started by :func:`start` would run its 4 ms task every 15.6 ms (and SoftMotion
    would move everything at a quarter speed). Returns True if the setting was applied.
    """
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(_PROCESS_SET_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        mask = _THROTTLING_IGNORE_TIMER_RESOLUTION | _THROTTLING_EXECUTION_SPEED
        state = _PowerThrottlingState(_THROTTLING_VERSION, mask, 0)
        ok = kernel32.SetProcessInformation(
            wintypes.HANDLE(handle),
            _PROCESS_POWER_THROTTLING,
            ctypes.byref(state),
            ctypes.sizeof(state),
        )
        return bool(ok)
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(handle))


def _launch(settings: RuntimeSettings) -> int:
    log = (_state_dir() / "runtime.log").open("wb")
    proc = subprocess.Popen(
        [str(settings.executable), "-d"],
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=_CREATE_NO_WINDOW | _DETACHED_PROCESS,
    )
    _pid_file().write_text(str(proc.pid), encoding="utf-8")
    disable_timer_throttling(proc.pid)
    return proc.pid


def _wait_for_port(port: int, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if port_open(port):
            return True
        time.sleep(0.5)
    return False


def start(settings: RuntimeSettings) -> int:
    """Start the soft-PLC (configured as in ``settings``) unless it already runs.

    On the very first start the runtime creates its data folder; it is then stopped once, the
    settings are applied and it is started again.

    Returns:
        The runtime's process id.

    Raises:
        RuntimeError: If the runtime does not open its programming port in time.
    """
    pid = _read_pid()
    if pid is not None and process_alive(pid):
        return pid
    cfg = find_runtime_cfg(settings)
    if cfg is None:
        first = _launch(settings)
        if not _wait_for_port(settings.opcua_port, settings.start_timeout_s):
            stop()
            msg = "the runtime did not create its configuration"
            raise RuntimeError(msg)
        stop()
        cfg = find_runtime_cfg(settings)
        if cfg is None:
            msg = f"no {CFG_NAME} under {settings.data_dir} after the first start (pid {first})"
            raise RuntimeError(msg)
    apply_runtime_settings(cfg, settings)
    pid = _launch(settings)
    if not _wait_for_port(settings.opcua_port, settings.start_timeout_s):
        stop()
        msg = f"the runtime did not open OPC UA port {settings.opcua_port} within the timeout"
        raise RuntimeError(msg)
    return pid


def inbound_allowed_from_rules(rules: str) -> bool:
    """Parse ``Enabled|Action|Direction`` lines; True if an enabled inbound Allow rule exists."""
    for line in rules.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if parts == ["True", "Allow", "Inbound"]:
            return True
    return False


def firewall_allows_inbound(executable: Path) -> bool:
    """Return True if an enabled Windows firewall rule lets the network reach ``executable``."""
    script = (
        "Get-NetFirewallApplicationFilter | Where-Object { $_.Program -eq '"
        + str(executable).replace("'", "''")
        + "' } | Get-NetFirewallRule | ForEach-Object { \"$($_.Enabled)|$($_.Action)|"
        '$($_.Direction)" }'
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return inbound_allowed_from_rules(out)


def stop() -> bool:
    """Stop the soft-PLC started by :func:`start`. Returns True if a process was stopped."""
    pid = _read_pid()
    _pid_file().unlink(missing_ok=True)
    if pid is None or not process_alive(pid):
        return False
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
    return True


_APP = "ns=4;s=|var|CODESYS Control Win V3 x64.Application."
STATE_NODE = _APP + "GVL_Bridge.eState"
SEQ_NODE = _APP + "GVL_Bridge.udiSetpointSeq"  # +1 per MainTask cycle


async def read_packml_state(
    endpoint: str, timeout_s: float = 4.0, sample_s: float = 2.0
) -> tuple[int | None, float | None]:
    """Read ``GVL_Bridge.eState`` and measure the MainTask period over ``sample_s`` seconds.

    Returns:
        (PackML state, MainTask period in ms); None where the application is not reachable.
    """
    try:
        async with Client(endpoint, timeout=timeout_s) as client:
            value: object = await client.get_node(STATE_NODE).read_value()
            seq = client.get_node(SEQ_NODE)
            first: object = await seq.read_value()
            start = time.perf_counter()
            await asyncio.sleep(sample_s)
            last: object = await seq.read_value()
            elapsed = time.perf_counter() - start
    except (OSError, TimeoutError, ua.UaError):
        return None, None
    state = int(value) if isinstance(value, int) else None
    period = None
    if isinstance(first, int) and isinstance(last, int) and last > first:
        period = elapsed * 1000.0 / (last - first)
    return state, period


def status(settings: RuntimeSettings, endpoint: str | None = None) -> RuntimeStatus:
    """Report whether the runtime process and its ports are up, and the PackML state."""
    pid = _read_pid()
    opcua_open = port_open(settings.opcua_port)
    state = period = None
    if opcua_open:
        url = endpoint or f"opc.tcp://127.0.0.1:{settings.opcua_port}"
        state, period = asyncio.run(read_packml_state(url))
    return RuntimeStatus(
        pid=pid,
        process_alive=pid is not None and process_alive(pid),
        programming_port_open=port_open(settings.programming_port),
        opcua_port_open=opcua_open,
        packml_state=state,
        main_task_period_ms=period,
    )


def read_dotenv(path: Path) -> dict[str, str]:
    """Read ``KEY=VALUE`` lines of a ``.env`` file (comments and blank lines ignored)."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def deploy(settings: RuntimeSettings, project: Path) -> str:
    """Download the PLC application to the running soft-PLC and start it (headless IDE).

    The IDE works on a temporary copy, so the project in the repository is never modified or
    locked. Credentials for the runtime's initial user come from ``.env``
    (``AIRC_PLC_USER``, ``AIRC_PLC_PASSWORD``).

    Returns:
        The deploy log.

    Raises:
        RuntimeError: If the deploy script does not report success.
    """
    root = repo_root()
    secrets = read_dotenv(root / ".env")
    missing = [k for k in ("AIRC_PLC_USER", "AIRC_PLC_PASSWORD") if not secrets.get(k)]
    if missing:
        msg = f"missing in .env: {', '.join(missing)} (see .env.example)"
        raise RuntimeError(msg)
    script = root / "plc" / "scripts" / "deploy_runtime.py"
    log_path = root / "plc" / "scripts" / "deploy_runtime.log"
    with tempfile.TemporaryDirectory(prefix="airc-deploy-") as tmp:
        copy = Path(tmp) / project.name
        shutil.copy2(project, copy)
        env = {
            **os.environ,
            **{k: secrets[k] for k in ("AIRC_PLC_USER", "AIRC_PLC_PASSWORD")},
            "AIRC_DEPLOY_PROJECT": str(copy),
            "AIRC_DEPLOY_LOG": str(log_path),
            "AIRC_GATEWAY_PORT": str(settings.gateway_port),
        }
        # CODESYS parses its own command line and expects --profile="<name>" with the quotes
        # inside the argument, which a list of arguments cannot express on Windows.
        command = (
            f'"{settings.ide_executable}" --profile="{settings.ide_profile}" '
            f'--noUI --runscript="{script}"'
        )
        subprocess.run(
            command,
            env=env,
            timeout=settings.deploy_timeout_s,
            check=False,
            capture_output=True,
        )
    log = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
    if DEPLOY_OK not in log:
        msg = f"deploy failed, see {log_path}:\n{log[-2000:]}"
        raise RuntimeError(msg)
    return log
