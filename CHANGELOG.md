# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
