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
2. Unit-test in simulation: `codesys_sim_start` → `codesys_sim_force`/`codesys_sim_write` →
   `codesys_sim_cycle` → `codesys_sim_read` → `codesys_sim_stop`. Constants are inlined and cannot
   be read online; read a variable initialised from them instead.
3. `export_sources dir=<repo>/plc/src`; commit the `.project` and the export together. A second
   export without changes must write 0 files.

Extended in phase P1 (PackML, alarms, test harness patterns).
