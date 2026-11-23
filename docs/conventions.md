# Conventions

The standing rulebook for this repository. The design rationale is in
[`specs/2026-11-23-system-design.md`](specs/2026-11-23-system-design.md) §11.

## 1. CODESYS / IEC 61131-3

### 1.1 Object names

| Element | Rule | Example |
|---|---|---|
| Function block | `FB_` + PascalCase | `FB_VacuumGripper` |
| Function | `F_` | `F_DegToRad` |
| Program | `PRG_` | `PRG_Main` |
| Interface | `I_` | `I_Equipment` |
| Struct | `ST_` | `ST_PartRecord` |
| Enum | `E_` (values PascalCase) | `E_PackMLState.Execute` |
| Union / Alias | `U_` / `T_` | `T_PartId` |
| Global variable list | `GVL_` | `GVL_Bridge` |
| Method / Property | PascalCase verb / noun | `Reset()`, `IsReady` |
| Application folder | PascalCase IEC identifier, no numeric prefix | `Equipment` |

### 1.2 Variable prefixes

| Type | Prefix | Example |
|---|---|---|
| BOOL | `x` | `xEnable` |
| BYTE / WORD / DWORD / LWORD | `by` / `w` / `dw` / `lw` | `wStatus` |
| SINT / INT / DINT / LINT | `si` / `i` / `di` / `li` | `iCount` |
| USINT / UINT / UDINT / ULINT | `usi` / `ui` / `udi` / `uli` | `udiPartId` |
| REAL / LREAL | `r` / `lr` | `lrPosition` |
| STRING / WSTRING | `s` / `ws` | `sName` |
| TIME / LTIME | `t` / `lt` | `tTimeout` |
| Enum | `e` | `eState` |
| Struct instance | `st` | `stPart` |
| FB instance | `fb` | `fbRobot` |
| Interface reference | `itf` | `itfAxis` |
| Array | `a` | `aBins` |
| Pointer / Reference | `p` / `ref` | `pData`, `refAxis` |

Constants are `UPPER_SNAKE_CASE` in `GVL_Constants` (or a domain GVL marked `CONSTANT`).

### 1.3 Rules

- Structured Text everywhere. SFC is allowed for the pick sequence if it reads better.
- `PRG_*` programs only instantiate and call. No logic.
- No magic numbers. Use named constants or recipe parameters.
- Every GVL and enum carries `{attribute 'qualified_only'}`.
- Every equipment FB implements `I_Equipment`.
- Before calling a library FB, check its interface (`get_signature` in the MCP toolkit).
- Re-export `plc/src/` before every commit that changes the project (see `plc/scripts/README.md`).

### 1.4 Function block header template

```iecst
(*
    FB_<Name>
    Purpose : <one sentence>
    Inputs  : <name> - <meaning, unit>
    Outputs : <name> - <meaning, unit>
    States  : <state machine summary, if any>
    Alarms  : <alarm ids raised, if any>
*)
FUNCTION_BLOCK FB_<Name> IMPLEMENTS I_Equipment
```

## 2. Python

- Python 3.12, uv, `src/` layout, package `airc`.
- ruff (lint + format, line length 100) and pyright strict on `src/airc`.
- Type hints everywhere; pydantic models for configuration and messages.
- Modules `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- asyncio for the bridge and I/O; no blocking calls in the bridge loop.
- Configuration only from `config/*.yaml` (secrets from environment variables). No hard-coded IPs or paths.
- Tests first (pytest). Tests live under `tests/unit`, `tests/integration`, `tests/plc`.

### 2.1 Module docstring template

```python
"""<One-line summary>.

<What this module owns, what it must not do, and which spec section it implements.>
"""
```

## 3. Git

- Branches: `main` (always working), `phase/<n>-<topic>`, `feat/…`, `fix/…`, `docs/…`.
- Commits: [Conventional Commits](https://www.conventionalcommits.org/), e.g. `feat(plc): add vacuum gripper FB`.
- No AI co-author trailers or "generated with" lines in commits, PRs or docs.
- Each phase merges into `main` through a pull request.
- Never commit model weights, videos, `.venv`, `.env*` or CODESYS build artefacts.

## 4. Files

- Docs and folders: `kebab-case`, except where a tool requires otherwise (Python modules, CODESYS objects).
- Architecture decision records: `docs/adr/NNNN-title.md`, Nygard format.
- Diagrams: editable `.drawio` source next to its exported `.svg` in `docs/architecture/diagrams/`.
