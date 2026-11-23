# 4. CODESYS SoftMotion for robot kinematics and motion

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

The robot arm has six axes and must pick parts from a moving conveyor. The project's subject
is PLC-based robot control, so the motion stack should be the industrial one.

## Decision

Use CODESYS SoftMotion (SM3_Robotics 4.20): an axis group of six virtual drives with the
built-in 6-DOF articulated kinematics, PTP and linear moves, and conveyor tracking. The robot
is a generic 6-axis arm with a spherical wrist; its MJCF model uses link lengths identical to
the CODESYS kinematics parameters. Exact function block names are verified against the
installed library before use.

Rejected: own inverse kinematics in Structured Text (re-implements a solved problem, risky).

## Consequences

- Path planning, blending, limits, jog and conveyor tracking come from a maintained library.
- A forward-kinematics consistency test between the PLC and the twin is required.
- No vendor robot model or branding is used.
