---
name: softmotion-robotics
description: Use when configuring or programming the 6-axis robot in CODESYS SoftMotion (SM3_Robotics, SM3_Transformation) - virtual drives, axis group, kinematics parameters, PTP and linear moves, conveyor tracking, jog, motion error handling - and the PLC-side supervision of the twin's servo joints.
---

# SoftMotion robotics (this project)

Design: spec §3.3, §4.2, §5; ADR 0004.

## Architecture rules

- Six **virtual drives** (`SM_Drive_Virtual`) form one axis group with the built-in 6-DOF
  articulated kinematics (spherical wrist). The conveyor is a separate virtual axis.
- The PLC generates trajectories; the **servo loop lives in the MuJoCo twin**. The twin returns
  measured joint position, velocity and torque via OPC UA (20 ms).
- `FB_JointMonitor` compares setpoint and measured values: following-error warning/error
  thresholds, torque-limit and stall detection, encoder plausibility. These raise AlarmManager alarms.
- The MJCF robot uses link lengths **identical** to the kinematics parameters; a forward-kinematics
  consistency test (PLC TCP vs. twin TCP) must pass.
- Motion runs in `MotionTask` (2 ms); `PRG_Motion` only calls FBs.

## Working rules

- Verify every SM3 FB with the MCP tool's `get_signature` / `get_library_api` before use.
  Installed: SM3_Robotics 4.20.1.0, SM3_Transformation 4.20.0.0.
- No motion unless: group powered AND no critical alarm AND (door closed OR Manual mode at reduced speed).
- Every move FB's `Error`/`ErrorID` is mapped to an alarm carrying the SoftMotion error id.

Extended in phase P1 (exact FB names, parameter tables, tracking sequence, jog limits).
