---
name: codesys-st-conventions
description: Use when writing, reviewing or refactoring any CODESYS IEC 61131-3 Structured Text in this repo (POUs, FBs, interfaces, DUTs, GVLs), or when exporting the PLC project for git. Covers naming prefixes, OOP rules, the FB header template and the MCP export workflow.
---

# CODESYS ST conventions (this project)

Authoritative rules: `docs/conventions.md` §1. This skill is the working checklist.

## Before writing code

1. Open the project with the CODESYS MCP tool: `open_project plc/RobotCell.project`, then `open_sim_panel`.
2. Read neighbours first: `get_outline` for the folder you are adding to.
3. For any library FB: `get_signature` before calling it. Never guess parameters.

## Names

- Objects: `FB_`, `F_`, `PRG_`, `I_`, `ST_`, `E_`, `U_`, `T_`, `GVL_`; methods/properties PascalCase.
- Variables: Hungarian type prefix + PascalCase: `xEnable`, `udiPartId`, `lrPos`, `eState`,
  `stPart`, `fbRobot`, `itfAxis`, `aBins`, `tTimeout`.
- Constants: `UPPER_SNAKE_CASE` in `GVL_Constants`.
- Application folders are IEC identifiers (no leading digits): `Config`, `Types`, `Interfaces`,
  `Framework`, `Equipment`, `Process`, `Comm`, `Programs`, `Tests`.

## OOP rules

- Equipment FBs implement `I_Equipment` (`Enable`, `Reset`, `Stop`, `Abort`; `State`, `HasError`, `ErrorId`).
- Use `FB_init` for wiring references, not cyclic inputs. Call `SUPER^` explicitly when overriding.
- Pass collaborators as interface references (`itf…`), not concrete FB types.
- `{attribute 'qualified_only'}` on every GVL and enum; `{attribute 'strict'}` on enums.
- `PRG_*` only instantiate and call. No logic, no magic numbers.

## FB header

```iecst
(*
    FB_<Name>
    Purpose : <one sentence>
    Inputs  : <name> - <meaning, unit>
    Outputs : <name> - <meaning, unit>
    States  : <summary>
    Alarms  : <ids>
*)
```

## Verify, then export

1. `compile` with `check_all: true, deep: true`: must report **0 errors, 0 warnings**.
2. Before simulation tests run `python tools/uv_run.py airc plc unthrottle-ide`: Windows 11
   throttles the windowless IDE, and its simulation then runs at ~25 % of real time, which breaks
   the specs' real-time waits.
3. Unit-test in simulation: `codesys_sim_start` → `codesys_sim_force`/`codesys_sim_write` →
   `codesys_sim_cycle` → `codesys_sim_read` → `codesys_sim_stop`. Constants are inlined and cannot
   be read online; read a variable initialised from them instead.
4. `export_sources dir=<repo>/plc/src`; commit the `.project` and the export together. A second
   export without changes must write 0 files.

## Gotchas found in Phase 1

- Reserved names cannot be used for methods: `Add`, `IndexOf` (use `AddRecord`, `FindPart`).
- Object/folder names must be IEC identifiers (no leading digit).
- Methods of an FB must not use its `VAR_IN_OUT` references; do that work in the FB body
  (methods only touch the FB's own variables).
- Unreferenced global variables are not linked: tests read them through a harness output.
- Enum inputs are written in simulation tests as integers; expectations use symbolic names.
- Placeholder libraries are removed by their `#Name`.

## Simulation test pattern

1. Write `tests/plc/<area>.json` (or a generator in `tests/plc/generators/`) first.
2. Add a harness program `PRG_Test<Area>` in `Tests`, called by `PRG_Tests` (MainTask). Logic-only
   harnesses may re-initialise by assigning a fresh instance; SoftMotion harnesses must not
   (gate with `xActive` instead).
3. Compile → RED (unknown FB) → implement → compile 0/0 → `codesys_sim_start {run: true}` →
   `codesys_sim_test` → `codesys_sim_stop`.
4. Time-based cases use `waitMs` (the app keeps running); `cycles` stops the app, so do not mix
   them in one session. Tool writes take ~100 ms: generate short pulses inside the harness.
5. `export_sources`, commit.
