# PLC project workflow

`plc/RobotCell.project` is the CODESYS V3.5 SP22 Patch 4 project (binary).
`plc/src/` is its **text export**: one `.st` file per POU/DUT/GVL plus `project.txt`
(tasks, libraries, devices, alarms). The export is what reviewers read on GitHub.

## Opening the project

1. Install CODESYS 3.5.22.40 with SoftMotion 4.20 (see `docs/user-guide/setup.md`).
2. Open `plc/RobotCell.project` in CODESYS. Device: **CODESYS Control Win V3 x64**.

## Rule: re-export before every commit that touches the PLC

The export is produced with the CODESYS MCP toolkit (`@codesys/mcp-toolkit`):

```text
export_sources  dir = <repo>/plc/src
```

The export is deterministic: running it again without changes writes 0 files. Files use LF line
endings. Do not hand-edit files in `plc/src/`; change the project and re-export.

## How the project was built

CODESYS accepts a `SoftMotion General Axis Pool` only on a device that was created with SoftMotion;
a device made from the plain `Standard.project` template refuses it. The SoftMotion base is
therefore derived from the official SoftMotion tutorial *Robotics_Jogging* by a script:

```powershell
& "C:\Program Files\CODESYS 3.5.22.40\CODESYS\Common\CODESYS.exe" --profile="CODESYS V3.5 SP22 Patch 4" --noUI --runscript="plc\scripts\build_softmotion_base.py"
```

It writes `plc/RobotCell.base.project`, which has:
- the device upgraded to Control Win V3 x64 3.5.22.40
- drives `Axis_J1`…`Axis_J6` and `Axis_Conveyor`
- axis group `AxisGroup_Robot` (`TRAFO.Kin_ArticulatedRobot_6DOF`), generated from `templates/AxisGroup_Robot.export`

The task configuration, drive parameters (below), folders and POUs were then added with the MCP
toolkit.

### Kinematics (`Kin_ArticulatedRobot_6DOF`, mm)

| a1 | d1 | a2 | a3 | d3 | d4 | d6 |
|---|---|---|---|---|---|---|
| 50 | 400 | 450 | 50 | 0 | 450 | 120 (incl. suction tool) |

### Drive parameters (`SM_Drive_Virtual`)

Movement type `c0/1060`: **1 = finite** (0 = modulo; joints must be finite, or `MC_GroupEnable`
fails with `SMC_MODULO_AXIS_FOR_LIMITED_ROTARY_JOINT`).

| Axis | SW limits (°) | v max | a/d max | jerk max |
|---|---|---|---|---|
| Axis_J1 | −170 … +170 | 180 °/s | 1000 °/s² | 10000 °/s³ |
| Axis_J2 | −90 … +150 | 180 °/s | 1000 | 10000 |
| Axis_J3 | −120 … +150 | 180 °/s | 1000 | 10000 |
| Axis_J4 | −180 … +180 | 360 °/s | 1000 | 10000 |
| Axis_J5 | −120 … +120 | 360 °/s | 1000 | 10000 |
| Axis_J6 | −360 … +360 | 360 °/s | 1000 | 10000 |
| Axis_Conveyor | none (mm) | 400 mm/s | 1000 mm/s² | 10000 mm/s³ |

### Tasks

| Task | Type | Calls | Note |
|---|---|---|---|
| `MainTask` | cyclic 4 ms, prio 1 | `PRG_Main`, `PRG_Tests` | SoftMotion bus cycle task (highest priority) |
| `SoftMotion_PlanningTask` | freewheeling, prio 15 | — | used by the robotics planner |
| `CommTask` | cyclic 50 ms, prio 10 | `PRG_Comm` | OPC UA consistency (Phase 2) |

## PLC tests

Simulation test specs live in `tests/plc/*.json`; each file is the `cases` argument of the MCP
toolkit's `codesys_sim_test`. Run: `codesys_sim_start {run: true}` → `codesys_sim_test` with the
file's cases → `codesys_sim_stop`. Test harness programs live in the `Tests` folder and are called
by `PRG_Tests`. CI checks that every spec file is well formed (`tests/unit/test_plc_test_specs.py`).

## Scripts

| Script | Purpose |
|---|---|
| `build_softmotion_base.py` | Builds the SoftMotion base project (see above). |
| `set_device_x64.py` | Switches a project's root device to Control Win V3 x64 (used in Phase 0). |

## Demo licence

Without a licence, CODESYS Control Win runs in demo mode and stops after about two hours.
Restart the `CODESYS Control Win V3 - x64` service (or the simulation) to continue.

## Program organisation

Application folders (spec §5.2): `Config`, `Types`, `Interfaces`, `Framework`, `Equipment`,
`Process`, `Comm`, `Programs`, `Tests`.
