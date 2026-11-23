# 1. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

The project spans a PLC program, Python services, a simulator, an HMI and a paper. Decisions
made early (simulator, protocol, AI services) shape every later phase and must be explainable
to reviewers and in the paper.

## Decision

Record each significant architecture decision as a short ADR in `docs/adr/`, using
Michael Nygard's format (Title, Status, Context, Decision, Consequences). The approved system
design (`docs/specs/2026-11-23-system-design.md`) remains the authoritative description;
ADRs capture the reasoning behind individual choices.

## Consequences

- New decisions get a new numbered ADR; superseded ones are marked `Superseded by NNNN`.
- The paper's design-rationale text can be traced back to ADRs.
