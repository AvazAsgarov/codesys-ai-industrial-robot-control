# PLC project workflow

`plc/RobotCell.project` is the CODESYS V3.5 SP22 Patch 4 project (binary).
`plc/src/` is its **text export** — one `.st` file per POU/DUT/GVL plus `project.txt`
(tasks, libraries, devices, alarms). The export is what reviewers read on GitHub.

## Opening the project

1. Install CODESYS 3.5.22.40 with SoftMotion (see `docs/user-guide/setup.md`).
2. Open `plc/RobotCell.project` in CODESYS. Device: **CODESYS Control Win V3 x64**.

## Rule: re-export before every commit that touches the PLC

The export is produced with the CODESYS MCP toolkit (`@codesys/mcp-toolkit`):

```text
export_sources  dir = <repo>/plc/src
```

The export is deterministic: running it again without changes writes 0 files.
Files use LF line endings. Do not hand-edit files in `plc/src/`; change the project and
re-export.

## Scripts

| Script | Purpose |
|---|---|
| `set_device_x64.py` | CODESYS IronPython script that switches the root device to Control Win V3 x64 (used once when the project was created from CODESYS's standard template, which defaults to the x86 device). |

## Demo licence

Without a licence, CODESYS Control Win runs in demo mode and stops after about two hours.
Restart the `CODESYS Control Win V3 - x64` service (or the simulation) to continue.

## Program organisation

Application folders (spec §5.2): `Config`, `Types`, `Interfaces`, `Framework`, `Equipment`,
`Process`, `Comm`, `Programs`, `Tests`. Tasks: `MotionTask` 2 ms (prio 1) → `PRG_Motion`,
`MainTask` 10 ms (prio 5) → `PRG_Main`, `CommTask` 50 ms (prio 10) → `PRG_Comm`.
