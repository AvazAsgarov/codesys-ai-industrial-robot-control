# Phase 0 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the public repository `codesys-ai-industrial-robot-control` with its full skeleton: layout, conventions, Python package and tooling, CI, paper skeleton, an empty CODESYS project that compiles, project docs and Claude skills. Every later phase builds on this.

**Architecture:** A single repo with a `src/`-layout Python package `airc` (managed by uv), a CODESYS project under `plc/` with a reviewable text export, a LaTeX paper under `paper/`, and docs under `docs/`. CI runs everything that does not need CODESYS.

**Tech Stack:** Git + GitHub CLI, Python 3.12 + uv, ruff, pyright, pytest, pre-commit, Typer, pydantic v2, PyYAML, GitHub Actions, Tectonic (LaTeX, IEEEtran), CODESYS V3.5 SP22 P4 via the CODESYS MCP toolkit, draw.io.

**Spec:** `docs/specs/2026-11-23-system-design.md` (approved 2026-11-23). Read §10 (layout), §11 (conventions), §13 (skills), §15 (P0 exit criteria) before starting.

## Global Constraints

- Repo root: `C:\dev\codesys-ai-industrial-robot-control` (outside OneDrive). Remote: `github.com/AvazAsgarov/codesys-ai-industrial-robot-control`, **public**.
- Everything in English.
- Licence: **AGPL-3.0**.
- Commits: Conventional Commits, author `AvazAsgarov <avaz.asgarov45@gmail.com>` (existing global git config). **No `Co-Authored-By` trailers and no "Generated with Claude Code" lines anywhere**, including PR bodies.
- Branches: `main` holds only the bootstrap commit; all P0 work goes on `phase/0-foundation` and is merged by PR.
- Python `>=3.12,<3.13`, package name `airc`, `src/` layout, uv lockfile committed.
- Python style: ruff lint + format, line length 100, pyright **strict** on `src/airc`.
- No hard-coded paths or endpoints in Python; configuration comes from `config/*.yaml`.
- Never commit model weights, videos, `.venv`, CODESYS runtime/compile artefacts. Pre-commit blocks files > 1 MB, except `plc/RobotCell.project`.
- CODESYS naming per spec §11.1 (`FB_`, `PRG_`, `I_`, `ST_`, `E_`, `GVL_`, Hungarian variable prefixes, `{attribute 'qualified_only'}` on GVLs).
- Heavy runtime dependencies (mujoco, ultralytics, openvino, asyncua, thx02) are **not** added in P0. Each one arrives with the phase that uses it.

## Review Focus

1. **Running the CLI from a different working directory.** `airc` must find `config/cell.yaml` relative to the repo root (or `--config`), not the CWD. Test: `test_load_config_default_path_independent_of_cwd` (Task 2).
2. **A malformed or partial `cell.yaml`.** It must fail with a clear message naming the bad key, not a stack trace from deep inside pydantic. Tests: `test_load_config_unknown_key_rejected`, `test_cli_bad_config_exit_code` (Task 2).
3. **Windows line endings and CODESYS text exports.** `.gitattributes` must keep `.st`/`.xml` exports stable so diffs don't churn. Check: `git diff --stat` empty after a re-export with no changes (Task 6).
4. **Secrets leaking into a public repo** (`.env`, API keys). `.gitignore` must cover `.env*`, and pre-commit runs `detect-private-key`. Check in Task 3.
5. **CI passing locally but failing on GitHub** (path separators, missing LaTeX packages). CI runs on `ubuntu-latest` **and** `windows-latest` for Python, and the paper builds with Tectonic in CI. Check: first PR shows all jobs green (Task 8).

---

## File Structure (created in P0)

```
codesys-ai-industrial-robot-control/
├── .claude/skills/{codesys-st-conventions,softmotion-robotics,isa101-hmi,mujoco-twin,ieee-paper}/SKILL.md
├── .github/workflows/ci.yml
├── .github/ISSUE_TEMPLATE/{bug_report.md,feature_request.md}
├── .github/pull_request_template.md
├── config/cell.yaml                     minimal cell config (project meta + paths), grows per phase
├── docs/specs/2026-11-23-system-design.md          (moved from old folder)
├── docs/plans/2026-11-23-phase-0-foundation.md     (this file, moved)
├── docs/adr/0001…0006-*.md
├── docs/architecture/architecture.md + diagrams/system-layers.drawio + .svg
├── docs/conventions.md
├── docs/user-guide/setup.md
├── plc/RobotCell.project, plc/src/**, plc/scripts/README.md
├── paper/main.tex, paper/sections/*.tex, paper/references.bib, paper/figures/.gitkeep
├── src/airc/__init__.py, cli.py, common/__init__.py, common/config.py
├── tests/unit/test_version.py, test_config.py, test_cli.py
├── tests/conftest.py
├── tools/build_paper.ps1
├── .editorconfig .gitattributes .gitignore .pre-commit-config.yaml
├── CLAUDE.md CHANGELOG.md LICENSE THIRD_PARTY.md README.md
└── pyproject.toml uv.lock
```

The empty folders from spec §10 that P0 does not fill (`assets/`, `experiments/`, `presentation/`, `media/`, `src/airc/{bridge,twin,vision,decision,evaluation}`, `tests/integration`, `tests/plc`, `docs/hmi`) are **not** created in P0. Each phase creates its own.

---

### Task 1: Repository bootstrap

**Files:**
- Create: `C:\dev\codesys-ai-industrial-robot-control\` with `README.md`, `LICENSE`, `.gitignore`, `.gitattributes`, `.editorconfig`, `CHANGELOG.md`, `THIRD_PARTY.md`
- Move: `docs/specs/2026-11-23-system-design.md` and `docs/plans/2026-11-23-phase-0-foundation.md` from the original planning folder (inside OneDrive) into the repo (copy, then delete the OneDrive copies once the commit exists)

**Interfaces:**
- Produces: a git repo with branch `main` (1 commit) and branch `phase/0-foundation` checked out.

- [ ] **Step 1:** Create the folder, `git init` (default branch `main` is already configured).
- [ ] **Step 2:** Write `LICENSE` from `gh api /licenses/agpl-3.0 --jq .body`, with the copyright line `Copyright (C) 2026 Avaz Asgarov`.
- [ ] **Step 3:** Write `README.md` as a placeholder: title, one-line description (exact text below), "Work in progress — see docs/specs" note, licence badge.
  Description: `Vision-guided 6-axis robot cell: CODESYS SoftMotion PLC, YOLO26 perception, THX-02 decision layer, MuJoCo digital twin, ISA-101 HMI.`
- [ ] **Step 4:** Write `.gitignore`: Python (`__pycache__/`, `.venv/`, `*.egg-info/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `htmlcov/`), env (`.env`, `.env.*`), IDE (`.vscode/` except `extensions.json`, `.idea/`), OS (`Thumbs.db`, `desktop.ini`), CODESYS (`*.~u`, `*.compileinfo`, `*.precompilecache`, `*.opt`, `*.bootinfo`, `*.bootinfo_guids`, `plc/**/*.project.bak`, `plc/**/*.backup`), LaTeX (`paper/build/`, `*.aux`, `*.log`, `*.out`, `*.synctex.gz`), data (`experiments/runs/`, `assets/models/*.pt`, `*.onnx`, `*.bin`, `*.safetensors`, `media/*.mp4`).
- [ ] **Step 5:** Write `.gitattributes`: `* text=auto eol=lf`; `*.ps1 text eol=crlf`; `*.project binary`; `*.png *.jpg *.gif *.pdf *.stl *.obj binary`; `plc/src/** text eol=crlf` (CODESYS writes CRLF; keeping it avoids churn, see Review Focus 3).
- [ ] **Step 6:** Write `.editorconfig`: root, utf-8, final newline, trim whitespace; indent 4 spaces for `*.py`, `*.st`; 2 spaces for `*.yaml`, `*.yml`, `*.json`, `*.md`, `*.tex`.
- [ ] **Step 7:** Write `CHANGELOG.md` (Keep a Changelog format, `## [Unreleased]`) and `THIRD_PARTY.md` (header + table columns: Component | Licence | Use | Source; first row: Ultralytics YOLO | AGPL-3.0 | detection (from P3) | github.com/ultralytics/ultralytics).
- [ ] **Step 8:** Commit on `main`: `git add -A && git commit -m "chore: bootstrap repository"`.
- [ ] **Step 9:** `git switch -c phase/0-foundation`. Copy the spec and this plan into `docs/specs/` and `docs/plans/`. Commit `docs: add approved system design and phase 0 plan`.
- [ ] **Step 10: Verify:** `git log --format="%an <%ae>%n%B" -2` shows the author `AvazAsgarov` and **no** `Co-Authored-By` line. `git status` is clean.

---

### Task 2: Python package, config loader and CLI

**Files:**
- Create: `pyproject.toml`, `src/airc/__init__.py`, `src/airc/cli.py`, `src/airc/common/__init__.py`, `src/airc/common/config.py`, `config/cell.yaml`
- Test: `tests/conftest.py`, `tests/unit/test_version.py`, `tests/unit/test_config.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Produces:
  - `airc.__version__: str` = `"0.1.0"`
  - `airc.common.config.REPO_ROOT: pathlib.Path` (resolved by walking up from the module to the first folder with `pyproject.toml`)
  - `airc.common.config.DEFAULT_CONFIG_PATH: Path` = `REPO_ROOT / "config" / "cell.yaml"`
  - `class ProjectInfo(BaseModel)`: `name: str`, `version: str`
  - `class PlcInfo(BaseModel)`: `project_file: Path` (relative to repo root), `opcua_endpoint: str`
  - `class CellConfig(BaseModel)`: `project: ProjectInfo`, `plc: PlcInfo`. All models use `model_config = ConfigDict(extra="forbid", frozen=True)`.
  - `class ConfigError(Exception)`
  - `def load_config(path: Path | None = None) -> CellConfig`, which raises `ConfigError` with a message that contains the offending key path (e.g. `plc.opcua_endpointt`) or `not found: <path>`
  - CLI entry point `airc` (Typer app `airc.cli:app`), commands: `airc --version`, `airc config show [--config PATH]` (prints validated config as YAML). Exit code 2 on `ConfigError`, with the message on stderr.

- [ ] **Step 1:** Write `pyproject.toml`: `[project]` name `airc`, version `0.1.0`, `requires-python = ">=3.12,<3.13"`, licence `AGPL-3.0-only`, dependencies `typer>=0.12`, `pydantic>=2.8`, `pyyaml>=6`. `[project.scripts] airc = "airc.cli:app"`. Build backend `hatchling`. `[dependency-groups] dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.6", "pyright>=1.1.380", "pre-commit>=3.8", "types-PyYAML"]`. `[tool.pytest.ini_options] testpaths=["tests"]`, `addopts="-q --strict-markers"`.
- [ ] **Step 2:** Write `config/cell.yaml`:
  ```yaml
  project:
    name: codesys-ai-industrial-robot-control
    version: 0.1.0
  plc:
    project_file: plc/RobotCell.project
    opcua_endpoint: opc.tcp://localhost:4840
  ```
- [ ] **Step 3: Write the failing tests**
  - `test_version.py::test_version_matches_pyproject`: `airc.__version__ == tomllib.load(pyproject)["project"]["version"]`.
  - `test_config.py::test_load_config_default` → `cfg.project.name == "codesys-ai-industrial-robot-control"`, `cfg.plc.opcua_endpoint == "opc.tcp://localhost:4840"`.
  - `test_config.py::test_load_config_default_path_independent_of_cwd` (Review Focus 1): `monkeypatch.chdir(tmp_path)`, then `load_config()` still succeeds.
  - `test_config.py::test_load_config_unknown_key_rejected` (Review Focus 2): write YAML with `plc.opcua_endpointt` to `tmp_path`, so `pytest.raises(ConfigError, match="opcua_endpointt")`.
  - `test_config.py::test_load_config_missing_file`: `pytest.raises(ConfigError, match="not found")`.
  - `test_config.py::test_load_config_empty_file`: an empty YAML file raises `ConfigError` (not `TypeError`).
  - `test_config.py::test_config_is_frozen`: assigning `cfg.project.name = "x"` raises `pydantic.ValidationError`.
  - `test_cli.py::test_cli_version`: `CliRunner().invoke(app, ["--version"])` → exit 0, output contains `0.1.0`.
  - `test_cli.py::test_cli_config_show`: exit 0, output contains `opc.tcp://localhost:4840`.
  - `test_cli.py::test_cli_bad_config_exit_code` (Review Focus 2): `["config", "show", "--config", bad_file]` → exit code 2, output contains the bad key, and no `Traceback` in the output.
- [ ] **Step 4:** `uv sync` then `uv run pytest`. Expected: **FAIL** (import errors).
- [ ] **Step 5:** Implement `__init__.py`, `common/config.py`, `cli.py` with the signatures above. Convert `pydantic.ValidationError` to `ConfigError` by joining each error's `loc` with `.`.
- [ ] **Step 6:** `uv run pytest`. Expected: **11 passed**.
- [ ] **Step 7:** `uv run airc --version` prints `airc 0.1.0`. Running `uv run airc config show` from `C:\` (using `--project` for uv) works.
- [ ] **Step 8:** Commit `feat(airc): add package skeleton, config loader and CLI` (include `uv.lock`).

---

### Task 3: Code-quality gates

**Files:**
- Modify: `pyproject.toml` (tool sections)
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1:** Add `[tool.ruff]` `line-length = 100`, `target-version = "py312"`, `src = ["src", "tests"]`; `[tool.ruff.lint] select = ["E","F","W","I","N","UP","B","SIM","RUF","PL","PT","ANN","D"]`, pydocstyle convention `google`, per-file ignore `tests/** = ["D","ANN","PLR2004"]`. Add `[tool.pyright]` `include = ["src","tests"]`, `strict = ["src/airc"]`, `pythonVersion = "3.12"`, `venvPath = "."`, `venv = ".venv"`.
- [ ] **Step 2:** Write `.pre-commit-config.yaml` with these hooks: `pre-commit-hooks` (`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `check-merge-conflict`, `detect-private-key`, `check-added-large-files` with `--maxkb=1024`, excluding `^plc/RobotCell\.project$`), `ruff-pre-commit` (`ruff` with `--fix`, `ruff-format`), and a local `pyright` hook (`uv run pyright`, `pass_filenames: false`, `types: [python]`). Pin every hook to its current latest tag (`pre-commit autoupdate`).
- [ ] **Step 3:** `uv run pre-commit install`, then `uv run pre-commit run --all-files`. Fix every finding in the code from Task 2 until the run is **all Passed**.
- [ ] **Step 4: Verify secret protection** (Review Focus 4): create a throw-away `.env` containing `HALX_API_KEY=sk-test`, run `git status --porcelain`, and expect `.env` **not** to be listed. Delete it.
- [ ] **Step 5:** `uv run pyright` → `0 errors`. `uv run pytest` → 11 passed.
- [ ] **Step 6:** Commit `chore: add ruff, pyright and pre-commit gates`.

---

### Task 4: Paper skeleton (IEEEtran + Tectonic)

**Files:**
- Create: `paper/main.tex`, `paper/sections/{01-introduction,02-related-work,03-system-architecture,04-plc-control,05-perception,06-decision-layer,07-digital-twin,08-hmi,09-evaluation,10-conclusion}.tex`, `paper/references.bib`, `paper/figures/.gitkeep`, `tools/build_paper.ps1`

**Interfaces:**
- Produces: `tools/build_paper.ps1` → `paper/build/main.pdf`. CI calls `tectonic -X compile paper/main.tex --outdir paper/build`.

- [ ] **Step 1:** Install Tectonic. It isn't in winget, so download the latest `*x86_64-pc-windows-msvc.zip` with `gh release download -R tectonic-typesetting/tectonic` into `C:\dev\tools\tectonic\` and add that folder to the user PATH. Verify: `tectonic --version`.
- [ ] **Step 2:** Write `main.tex`: `\documentclass[conference]{IEEEtran}`; packages `cite, amsmath, amssymb, graphicx, booktabs, siunitx, hyperref (hidelinks), xcolor`; working title **"A Vision-Guided, AI-Supervised Robotic Sorting Cell on an IEC 61131-3 Soft-PLC with a MuJoCo Digital Twin"** (changeable later); author block with placeholders `\IEEEauthorblockN{Author Name}` and the comment `% TODO(P7): real author metadata from owner`; abstract and keywords stubs; `\input` each section; `\bibliographystyle{IEEEtran}`, `\bibliography{references}`.
- [ ] **Step 3:** Each section file gets a `\section{}` heading and 2–4 `% TODO(Pn):` bullet comments saying what goes there, mapped to the spec sections.
- [ ] **Step 4:** Seed `references.bib` with entries **verified via the citation-management skill** (DOI/URL resolved, metadata matched): IEC 61131-3:2013, ISA-TR88.00.02 (PackML), ANSI/ISA-101.01, ISA-18.2, MuJoCo (Todorov et al., IROS 2012), OPC UA (IEC 62541), Ultralytics YOLO26 (software citation), YOLOE (arXiv), THX-02 (Hugging Face model card). Cite each once in its section stub so BibTeX keeps them.
- [ ] **Step 5:** Write `tools/build_paper.ps1`: runs Tectonic with `--outdir paper/build` and exits non-zero on failure.
- [ ] **Step 6: Verify:** `powershell -ExecutionPolicy Bypass -File tools/build_paper.ps1` → `paper/build/main.pdf` exists. Opening it shows the IEEE two-column layout, the title, all 10 section headings and a references list with 9 entries.
- [ ] **Step 7:** Commit `docs(paper): add IEEEtran paper skeleton and build script`.

---

### Task 5: CI workflow and GitHub templates

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/bug_report.md`, `.github/ISSUE_TEMPLATE/feature_request.md`

- [ ] **Step 1:** Write `ci.yml`. Trigger: `push` to `main` and `pull_request`. Concurrency group per ref, cancel-in-progress. Jobs:
  - `python`: matrix `os: [ubuntu-latest, windows-latest]`; steps: checkout → `astral-sh/setup-uv` (pin current major, `enable-cache: true`) → `uv sync --locked` → `uv run ruff check .` → `uv run ruff format --check .` → `uv run pyright` → `uv run pytest --cov=airc --cov-report=term-missing`.
  - `paper`: `ubuntu-latest`; checkout → `wtfjoke/setup-tectonic` (pin current major) → `tectonic -X compile paper/main.tex --outdir paper/build` → upload `paper/build/main.pdf` as artefact `paper-pdf`.
  Pin every action to its current major tag. Verify the tags exist with `gh api repos/<owner>/<repo>/releases/latest`.
- [ ] **Step 2:** Validate locally: `uv run pre-commit run check-yaml --files .github/workflows/ci.yml` passes. Optionally run `actionlint` via `uvx actionlint-py` if it installs.
- [ ] **Step 3:** Write the PR template (sections: Summary, Phase, Changes, How verified, Checklist: tests pass / docs updated / PLC export regenerated / no secrets) and the two issue templates (YAML front matter `name`, `about`, `labels`). No AI attribution text anywhere.
- [ ] **Step 4:** Commit `ci: add GitHub Actions workflow and templates`.

---

### Task 6: CODESYS project skeleton

**Files:**
- Create: `plc/RobotCell.project`, `plc/src/**` (export), `plc/scripts/README.md`

**Interfaces:**
- Produces: a project whose application tree matches spec §5.2 and whose task configuration matches spec §5.1. Later phases add POUs into these folders.

Use the CODESYS MCP tool (`mcp__codesys__codesys`, actions per its `help`). Call `open_sim_panel` right after creating the project so the owner can watch.

- [ ] **Step 1:** `create_project` at `C:\dev\codesys-ai-industrial-robot-control\plc\RobotCell.project` with device **CODESYS Control Win V3 x64** (standard project template).
- [ ] **Step 2:** Create the application folders `00_Config`, `01_Types`, `02_Interfaces`, `10_Framework`, `20_Equipment`, `30_Process`, `40_Comm`, `50_Programs`, `90_Tests`.
- [ ] **Step 3:** Create the thin programs in `50_Programs`: `PRG_Main`, `PRG_Motion`, `PRG_Comm`, each with a header comment (purpose, task, cycle) and an empty body. Create `GVL_Constants` in `00_Config` with `{attribute 'qualified_only'}` and one constant `PROJECT_VERSION : STRING := '0.1.0';`. Remove the template's default `PLC_PRG` if present.
- [ ] **Step 4:** Configure tasks: `MotionTask` cyclic **2 ms**, priority 1, calls `PRG_Motion`; `MainTask` cyclic **10 ms**, priority 5, calls `PRG_Main`; `CommTask` cyclic **50 ms**, priority 10, calls `PRG_Comm`. `VisuTask` (100 ms) is created by CODESYS when the first visualization is added in P5, so it isn't created now.
- [ ] **Step 5:** `compile`. Expected: **0 errors, 0 warnings** (fix any warning).
- [ ] **Step 6:** `codesys_sim_start` → `codesys_sim_cycle` (10 cycles) → `codesys_sim_read GVL_Constants.PROJECT_VERSION` = `'0.1.0'` → `codesys_sim_stop`. This proves the toolchain end to end.
- [ ] **Step 7:** `export_sources` to `plc/src/`. Then run the export a second time with no changes and confirm `git status --porcelain plc/src` is **empty** (Review Focus 3). If the export is not stable (timestamps, GUID order), note it in `plc/scripts/README.md` and add a normalising step.
- [ ] **Step 8:** Write `plc/scripts/README.md`: how to open the project, the MCP export workflow, the rule "re-export before every commit that touches the PLC", and the demo-licence note (Control Win stops after ~2 h; restart the service).
- [ ] **Step 9:** Commit `feat(plc): add CODESYS project skeleton with task configuration`.

---

### Task 7: Project docs, ADRs, architecture diagram, CLAUDE.md and project skills

**Files:**
- Create: `docs/conventions.md`, `docs/user-guide/setup.md`, `docs/architecture/architecture.md`, `docs/architecture/diagrams/system-layers.drawio` (+ `.svg` export), `docs/adr/0001-record-architecture-decisions.md`, `0002-mujoco-digital-twin.md`, `0003-opc-ua-plc-bridge.md`, `0004-softmotion-kinematics.md`, `0005-zero-shot-vision.md`, `0006-thx02-hosted-decision-layer.md`, `CLAUDE.md`, `.claude/skills/*/SKILL.md` (5 skills)

- [ ] **Step 1:** `docs/conventions.md`: spec §11 rewritten as the standing rulebook, plus an ST function-block header template and a Python module docstring template.
- [ ] **Step 2:** ADRs in Nygard format (Title, Status: Accepted, Context, Decision, Consequences), each ≤ 1 page, content taken from spec §3 and §18.
- [ ] **Step 3:** Architecture diagram with the **drawio-skill**: the five layers of spec §4.1 (Plant, L0–L3) plus the HMI, with the data flows of §4.2/§4.3 (setpoints, encoder feedback, sensor signals, part records, THX-02 calls) and their rates. Use the `corporate` style preset. Export the SVG and check it visually. `architecture.md` embeds the SVG and summarises §4 in ≤ 1 page.
- [ ] **Step 4:** `docs/user-guide/setup.md`: prerequisites (Windows 11, CODESYS 3.5.22.40 + SoftMotion, Python 3.12, uv, Git, Tectonic), clone, `uv sync`, `uv run pytest`, build paper, open PLC project. Every command in it must have been run successfully in Tasks 2–6.
- [ ] **Step 5:** `CLAUDE.md` (≤ 80 lines): project one-liner, pointers to the spec, conventions, plans; the hard rules (no AI attribution in commits/PRs/docs, English only, re-export PLC sources before committing, config not hard-coded, no weights in git); commands (test, lint, type, paper build); and which skills to use for which work.
- [ ] **Step 6:** Write the five project skills with **anthropic-skills:skill-creator** conventions (YAML front matter `name` + trigger-oriented `description`, body ≤ ~150 lines, P0 content only; each ends with "Extended in phase Pn"):
  - `codesys-st-conventions`: naming table, FB template, OOP rules (interfaces, `FB_init`, `SUPER^`), export workflow via the MCP tool.
  - `softmotion-robotics`: what is known now (virtual drives, axis group, the "verify every FB with `get_signature`" rule, servo-in-twin and supervision-in-PLC split per spec §4.2). Extended in P1.
  - `isa101-hmi`: ISA-101 principles, alarm priority colour rule, 1920×1080 grid, screen list from spec §9.2. Extended in P5.
  - `mujoco-twin`: MJCF conventions (units SI, naming `<part>_<role>`), sensor and actuator patterns, sync rule. Extended in P2.
  - `ieee-paper`: IEEEtran structure, "every number comes from `experiments/results/`" rule, figure and table style, the build command, and using citation-management for every new reference.
- [ ] **Step 7:** Proofread: every link in `docs/` resolves. Check with `uv run python -c` and a one-off script, or a manual pass.
- [ ] **Step 8:** Commit `docs: add conventions, ADRs, architecture, setup guide, CLAUDE.md and project skills`.

---

### Task 8: Publish to GitHub and exit Phase 0

- [ ] **Step 1:** `gh repo create AvazAsgarov/codesys-ai-industrial-robot-control --public --source . --remote origin --description "<Task 1 description>"`, then `git push -u origin main` and `git push -u origin phase/0-foundation`.
- [ ] **Step 2:** Set the topics: `gh repo edit --add-topic codesys,plc,iec-61131-3,structured-text,softmotion,robotics,industrial-automation,computer-vision,yolo,openvino,mujoco,digital-twin,opc-ua,hmi,packml`.
- [ ] **Step 3:** `gh pr create --base main --head phase/0-foundation --title "Phase 0: Foundation"` with a body from the PR template. **No AI attribution line.**
- [ ] **Step 4: Verify CI** (Review Focus 5): all jobs green (`python` on ubuntu and windows, `paper`). Fix and push until green. Download the `paper-pdf` artefact and confirm it opens.
- [ ] **Step 5:** Hand over to the owner for the P0 review: repo URL, PR URL, screenshot of the CODESYS project tree, and the paper PDF.
- [ ] **Step 6:** Before merging, update `CHANGELOG.md` `[Unreleased]` → `## [0.1.0] - <date>` with the P0 summary, and push it to the PR.
- [ ] **Step 7:** After the owner approves, `gh pr merge --squash` (subject `Phase 0: Foundation (#1)`, body without attribution), then delete the old OneDrive copies of the spec and plan.

**Phase 0 exit criteria (spec §15):** CI green; the empty CODESYS project compiles and runs in simulation; the owner has reviewed the repo skeleton.
