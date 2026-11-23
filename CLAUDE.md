# CLAUDE.md

Vision-guided 6-axis robot sorting cell: CODESYS SoftMotion PLC, YOLO26/YOLOE-26 perception,
THX-02 decision layer, MuJoCo digital twin, ISA-101 HMI. University final project, public repo.

## Read first

- Design (authoritative): `docs/specs/2026-11-23-system-design.md`
- Rules: `docs/conventions.md`
- Phase plans: `docs/plans/`
- Decisions: `docs/adr/`
- PLC workflow: `plc/scripts/README.md`

## Hard rules

- **No AI attribution anywhere**: no `Co-Authored-By` trailers, no "Generated with" lines in
  commits, PRs, docs or the paper.
- Everything in English.
- Re-export `plc/src/` (MCP toolkit `export_sources`) before committing any CODESYS change.
- No hard-coded paths, IPs or endpoints in Python; use `config/*.yaml`.
- Never commit weights, videos, `.venv`, `.env*`, or CODESYS build artefacts.
- Paper numbers come only from `experiments/results/` produced by scripts.
- Tests first (pytest for Python, simulation tests for PLC FBs).
- Phase work happens on `phase/<n>-<topic>` and merges by PR after the owner reviews it.

## Commands

```powershell
Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue  # machine sets it for another project
uv sync
uv run pytest
uv run ruff check . ; uv run ruff format --check . ; uv run pyright
uv run pre-commit run --all-files
powershell -ExecutionPolicy Bypass -File tools\build_paper.ps1
```

## Skills to use

| Work | Skill |
|---|---|
| Any CODESYS ST code | `codesys-st-conventions` (+ CODESYS MCP tool) |
| Axis group, kinematics, motion FBs | `softmotion-robotics` |
| HMI screens | `isa101-hmi`, then `impeccable` for critique |
| MuJoCo scene, sensors, sync | `mujoco-twin` |
| Paper text, figures, references | `ieee-paper`, `scientific-writing`, `citation-management` |
| Diagrams | `drawio-skill` |
| Planning / TDD / debugging | superpowers skills |

## Environment notes

- CODESYS 3.5.22.40 at `C:\Program Files\CODESYS 3.5.22.40`; device Control Win V3 x64.
- Demo licence: Control Win stops after ~2 h; restart the service.
- Laptop: Intel Core Ultra 7 255U, no NVIDIA GPU, 16 GB RAM. Use OpenVINO on CPU.
