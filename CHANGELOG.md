# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- 54 simulation test cases in `tests/plc/` (validated in CI) and ADR 0007.

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
