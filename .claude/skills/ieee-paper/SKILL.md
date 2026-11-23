---
name: ieee-paper
description: Use when writing or editing the project's IEEE-format LaTeX paper in paper/ (sections, figures, tables, references), or when building it. Enforces the IEEEtran structure, the results-sourcing rule and the build command.
---

# IEEE paper (this project)

## Structure

`paper/main.tex` (IEEEtran conference) inputs `paper/sections/01-…10-*.tex`:
Introduction, Related Work, System Architecture, PLC Control, Perception, AI Decision Layer,
Digital Twin, Operator Interface, Evaluation, Conclusion.

## Rules

- **Every number** in text, tables and figures comes from `experiments/results/`, produced by a
  script in the repo. Name the script in a LaTeX comment next to the number.
- Figures are vector (PDF) in `paper/figures/`; architecture diagrams come from
  `docs/architecture/diagrams/`. Captions are full sentences. Tables use `booktabs`; units use `siunitx`.
- References are added only through the `citation-management` workflow (DOI/arXiv → BibTeX, verified).
  Prefer published versions over preprints. Never invent metadata.
- `\cite` inside `%` comments does not count; every reference must be cited in visible text.
- Prose: use the `scientific-writing` skill. Active voice; past tense for what was done.
- No AI attribution or acknowledgement lines.
- Author metadata stays a placeholder until the owner provides it (P7).

## Build

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_paper.ps1   # → paper\build\main.pdf
```

Tectonic (XeTeX) builds locally and in CI. Fonts are loaded by file name (TeX Gyre Termes, Heros,
Cursor) because Tectonic has no fontconfig.

Extended in phase P7.
