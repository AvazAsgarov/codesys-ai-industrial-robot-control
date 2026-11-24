# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-11-24

Phase 2 — Digital twin and OPC UA bridge.

### Added

- Soft-PLC on CODESYS Control Win V3 x64 as a console process, started, deployed and checked by
  `airc plc start|deploy|status|stop` (headless IDE script); OPC UA anonymous on localhost only
  (ADR 0008).
- OPC UA bridge: single-source tag map (`config/opcua_tags.yaml`), batched async client with
  reconnect, operator commands over `GVL_Hmi`.
- MuJoCo digital twin generated from the PLC geometry: 6-axis arm with simulated servo drives
  (PD + velocity feed-forward, torque limits), conveyor carried by the PLC belt position, suction
  gripper, ray-cast photo-eyes, bins with fill level. Kinematics verified against CODESYS
  SoftMotion on 11 reference poses (0.5 mm / 0.1°).
- `airc run`: 20 ms twin-bridge cycle with a ground-truth stand-in for vision, seeded part supply
  and fault injection (E-stop, door, dropped part, full bin, lost bridge, blocked joint).
- Flight recorder in `airc run`: the last 50 cycles are logged when the cell leaves Execute through
  a fault.
- End-to-end tests on the real soft-PLC (`pytest -m codesys`): sorting by class, and recovery
  from an E-stop, a full bin, a lost bridge and an opened door.

### Changed

- `FB_JointMonitor` compares joint feedback with the setpoint sample it answers (128-sample
  history), so transport delay is not counted as following error; an error must persist for
  3 cycles (12 ms), so a torn OPC UA write cannot abort the cell.
  Feedback older than the setpoint history (a bridge hiccup within the watchdog) is not judged;
  if it stays that old for the feedback timeout it is stale.
- `airc plc start` refuses to start while a firewall rule exposes the runtime (`--allow-network`).

### Fixed

- HMI commands written during a PLC cycle could be lost (`PRG_Main` now clears only the command it
  has read).
- `airc plc stop` could kill an unrelated process that reused the runtime's process id.
- `airc plc deploy` could report success from the previous run's log.
- Parts stopped spawning for minutes after a PLC restart (the supply now follows belt travel).
- A capture whose vision write failed was never answered.
- Clearing could hang after a SoftMotion lag error: a reset answered "no error to reset" kept the
  fault latched, and re-enabling an already enabled group failed. The TCP lag tolerance is now set
  to 10 mm (the twin's servo lag is supervised by `FB_JointMonitor`).

## [0.2.0] - 2026-11-23

Phase 1 — PLC core.

### Added

- SoftMotion base project (reproducible build script): 6-axis articulated robot
  (`AxisGroup_Robot`, `Kin_ArticulatedRobot_6DOF`), conveyor axis, drive limits.
- PackML state machine (17 states, modes Production / Maintenance / Manual).
- Latching alarm handler with Critical / Error / Warning classes mapped to PackML.
- Equipment: robot (PLCopen-style command interface), conveyor, vacuum gripper, photo-eye, bins,
  safety monitor, joint following-error and feedback supervision, camera trigger.
- Part tracking with vision/decision message intake, deadline fallback and bin selection.
- Tracked pick-and-place sequence (`MC_TrackConveyorBelt`) from the moving belt.
- Sorting cell unit with interlocks, bridge watchdog and manual jogging.
- Standard and HighSpeed recipes.
- Fault recovery: errors stop the robot before resting in Error; a part still on the cup goes to
  quarantine after a reset; picks are abandoned at the window end; one-shot event alarms.
- 58 simulation test cases in `tests/plc/` (validated in CI) and ADR 0007.

## [0.1.0] - 2026-11-23

Phase 0 — Foundation.

### Added

- Approved system design, Phase 0 plan, conventions and six architecture decision records.
- Python package `airc`: validated, immutable cell configuration (`config/cell.yaml`,
  `--config`, `AIRC_CONFIG`) and the `airc` command-line interface.
- Quality gates: ruff, pyright (strict), pre-commit hooks with secret detection.
- IEEE paper skeleton (IEEEtran, ten sections, verified references) built with Tectonic.
- CI: Python checks on Ubuntu and Windows; paper PDF build and artifact.
- CODESYS project skeleton (Control Win V3 x64; 2/10/50 ms tasks) with a text export in `plc/src/`.
- Architecture diagram, setup guide, `CLAUDE.md` and project skills.
