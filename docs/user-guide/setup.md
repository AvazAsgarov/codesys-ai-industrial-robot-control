# Setup

Tested on Windows 11 (x64).

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| CODESYS | V3.5 SP22 Patch 4 (3.5.22.40) | With SoftMotion 4.20 and Visualization. Runs in demo mode without a licence (Control Win stops after ~2 h). |
| Python | 3.12 | |
| uv | latest | <https://docs.astral.sh/uv/> |
| Git | any recent | |
| Tectonic | 0.17+ | LaTeX engine for the paper; download the Windows zip from <https://github.com/tectonic-typesetting/tectonic/releases> and put `tectonic.exe` on `PATH`. |

## Clone and install

```powershell
git clone https://github.com/AvazAsgarov/codesys-ai-industrial-robot-control.git
cd codesys-ai-industrial-robot-control
uv sync
uv run pre-commit install
```

> **If `UV_PROJECT_ENVIRONMENT` is set on your machine** (for another project), uv will install
> into that environment instead of `.venv`. Clear it for this repository first:
> `Remove-Item Env:UV_PROJECT_ENVIRONMENT` (PowerShell, current session only).

## Check

```powershell
uv run pytest
uv run pre-commit run --all-files
uv run airc --version
uv run airc config show
```

## Build the paper

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_paper.ps1
```

Output: `paper\build\main.pdf`.

## Open the PLC project

Open `plc\RobotCell.project` in CODESYS 3.5.22.40. The device is **CODESYS Control Win V3 x64**.
See [`plc/scripts/README.md`](../../plc/scripts/README.md) for the export workflow.
