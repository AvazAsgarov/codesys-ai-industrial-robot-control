---
name: softmotion-robotics
description: Use when configuring or programming the 6-axis robot in CODESYS SoftMotion (SM3_Robotics, SM3_Transformation) - virtual drives, axis group, kinematics parameters, PTP and linear moves, conveyor tracking, jog, motion error handling - and the PLC-side supervision of the twin's servo joints.
---

# SoftMotion robotics (this project)

Design: spec §3.3, §4.2, §5; ADR 0004, ADR 0007; `docs/architecture/plc.md`.

## Base project (hard-won facts)

- A `SoftMotion General Axis Pool` is only accepted on a device created with SoftMotion; the plain
  Standard.project device refuses it ("cannot be added here"). The base is built from the official
  *Robotics_Jogging* example by `plc/scripts/build_softmotion_base.py` (opened with
  `VersionUpdateFlags.UpdateAll | SilentMode`, upgraded device, `save_as`).
- `SM_Drive_Virtual` movement type `c0/1060`: **1 = finite, 0 = modulo**. Robot joints must be
  finite, else `MC_GroupEnable` fails with `SMC_MODULO_AXIS_FOR_LIMITED_ROTARY_JOINT`. Device
  parameters are set with `configure_device` using the `c0/....` keys.
- Axis group config is a native-export object: `TRAFO.Kin_ArticulatedRobot_6DOF`, parameters a1,
  d1, a2, a3, d3, d4, d6 (mm), axis mapping, planning task `SoftMotion_PlanningTask`.
- SoftMotion runs in CODESYS's own simulation (`codesys_sim_start`).

## Rules

- All SoftMotion FBs are called every cycle in `MainTask` (the bus cycle task).
- **Never copy SoftMotion FB instances at runtime** (`fbA := fbInitial`): it corrupts their
  handles (spurious axis errors). Test harnesses gate calls with `xActive` instead.
- Only one owner may call `SMC_GroupPower`/`MC_Power` for an axis: `SMC_GroupPower(Enable := FALSE)`
  powers the group off. `GVL_Config.xCellEnabled` hands the robot to a test harness.
- Units: mm, mm/s, degrees. Orientation (A, B, C): **B = 180 is tool straight down** (measured).
  Tool-down pose used: A 0, B 180, C 180.
- `MC_MoveDirectAbsolute` has no Velocity input: use `VelFactor`/`AccFactor`/`JerkFactor`;
  `CoordSystem` ACS or MCS (PTP to a Cartesian target).
- `MC_GroupStop` validates `Deceleration`/`Jerk` even for PTP moves (`SMC_MOVE_INVALID_DYNAMICS`
  if 0).
- `MC_GroupSetOverride` errors while `MC_GroupStop` is active: enable it only when not stopping.
- Conveyor tracking: `MC_TrackConveyorBelt` (ConveyorBeltOrigin = belt frame in MCS,
  InitialObjectPosition = part in belt frame at the start, CoordSystem PCS_1); then linear moves
  in PCS_1. A new rising edge only after the PCS is no longer in use.
- Use linear moves only for short moves (tracked approach/descend/lift, retract); long transfers
  are PTP to avoid Cartesian singularities.
- `SMC_GroupJog2` needs non-zero VelFactor/AccFactor/JerkFactor and positive max distances.
- Verify every SM3 FB with `get_signature` before use.

## FB_Robot command interface

`eCmd` (`E_RobotCmd`: MovePtpAcs, MovePtpMcs, MoveLinMcs, MoveLinPcs1, Stop, Reset) + `stTarget`,
started by a rising edge of `xExecute`; outputs `xDone`/`xError`/`xBusy`. Callers drop `xExecute`
for one cycle between commands (see `FB_PickSequence` handshake).

Extended in Phase 2 (servo feedback from the twin, FK consistency test).
