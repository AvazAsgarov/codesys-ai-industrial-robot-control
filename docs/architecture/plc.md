# PLC architecture (Phase 1)

The CODESYS program runs the sorting cell as one PackML unit. Source: `plc/RobotCell.project`,
reviewable text export in [`plc/src/`](../../plc/src/). Build notes, drive parameters and the
kinematics are in [`plc/scripts/README.md`](../../plc/scripts/README.md); design decisions in
[ADR 0004](../adr/0004-softmotion-kinematics.md) and [ADR 0007](../adr/0007-plc-task-model-alarms-recipes.md).

## Object map

| Folder | Objects | Role |
|---|---|---|
| `Config` | `GVL_CellGeometry`, `GVL_Params` (RETAIN), `GVL_Config`, `GVL_AlarmDefs`, `GVL_Constants` | Geometry, process parameters, alarm definitions |
| `Types` | `E_PackMLState`, `E_PackMLMode`, `E_PackMLCommand`, `E_AlarmClass`, `E_AlarmId`, `E_Bin`, `E_Quality`, `E_DecisionSource`, `E_PartState`, `E_RobotCmd`, `E_PickStep`, `ST_PartRecord`, `ST_Alarm`, `ST_AlarmDef`, `ST_VisionMsg`, `ST_DecisionMsg`, `ST_CaptureMsg` | Data types |
| `Interfaces` | `I_Equipment`, `I_AlarmSink` | Contracts |
| `Framework` | `FB_PackMLStateMachine`, `FB_AlarmHandler`, `FB_PartQueue` | Reusable building blocks |
| `Equipment` | `FB_Robot`, `FB_Conveyor`, `FB_VacuumGripper`, `FB_PhotoEye`, `FB_Bin`, `FB_SafetyMonitor`, `FB_JointMonitor`, `FB_CameraTrigger` | One FB per physical module |
| `Process` | `FB_SortingCell`, `FB_PickSequence`, `FB_PartTracker`, `F_SelectBin` | Cell logic |
| `Comm` | `GVL_Bridge`, `GVL_Hmi`, `FB_MessageIntake`, `FB_BridgeWatchdog` | Exchange with the Python bridge and the HMI |
| `Programs` | `PRG_Main`, `PRG_Comm` | Thin entry programs |
| `Tests` | `PRG_Test*`, `PRG_Tests` | Simulation test harnesses |
| *(root)* | `PRG_Recipe_Cell`, `GVL_Recipe_Cell`, `ST_Recipe_Cell` | Generated recipes |

## Devices and tasks

| Item | Setting |
|---|---|
| Device | CODESYS Control Win V3 x64 3.5.22.40 |
| Axes | `Axis_J1`…`Axis_J6` (virtual, finite), `Axis_Conveyor` (virtual, finite, mm) |
| Axis group | `AxisGroup_Robot`, `Kin_ArticulatedRobot_6DOF` |
| `MainTask` | 4 ms, prio 1, bus cycle task → `PRG_Main`, `PRG_Tests`, `PRG_Recipe_Cell` |
| `SoftMotion_PlanningTask` | freewheeling, prio 15 |
| `CommTask` | 50 ms, prio 10 → `PRG_Comm` |

## PackML state actions (`FB_SortingCell`)

| State | Equipment action | Complete when |
|---|---|---|
| Resetting | acknowledge alarms, reset robot / gripper / conveyor | safe, robot ready, no Critical/Error alarm |
| Starting, Unholding, Unsuspending | robot home → ready pose, conveyor at speed (Manual: robot ready) | sequence waiting for parts and belt at speed |
| Execute | pick sequence runs (Manual: joint jogging) | — (producing state) |
| Stopping, Holding, Suspending, Completing | finish the current part, go home | sequence resting, robot and belt standing still |
| Aborting | controlled group stop, conveyor halt, **vacuum kept** | robot standing still, sequence aborted |
| Clearing | reset the sequence and equipment | safe, sequence idle, no Critical alarm |

Interlocks: Critical alarm or not safe → Abort; Error alarm → Stop; any bin full → Suspend, with an
automatic Unsuspend once the bin is emptied (an operator Suspend waits for the Unsuspend command).
Resetting and Clearing are not interrupted by the alarms they clear. HMI commands are one-shot:
`PRG_Main` consumes `GVL_Hmi.eCommand` every cycle.
Mode changes only in Stopped, Idle or Aborted. Maintenance and Manual-with-door-open run at 25 %.

## Pick-and-place sequence (`FB_PickSequence`)

`MoveHome` (PTP, ACS) → `MoveReady` (PTP to the ready pose above the belt) → `WaitPart`
(decided part furthest downstream in the pick window) → `StartTracking`
(`MC_TrackConveyorBelt`, PCS_1 follows the part) → `Approach` → `Descend` (linear in PCS_1) →
`Grip` (vacuum OK) → `Lift` (linear in PCS_1) → `MoveToBin` (PTP, MCS) → `Release` → `Retract`
→ `MoveReady`. Linear moves are used only for the short tracked moves; long transfers are PTP,
which avoids wrist and base singularities on Cartesian paths across the cell.

Faults: every error (tracking, motion, vacuum) first stops the robot (`Aborting`), then rests in
`Error`. A part lost in transfer keeps the valve on (no release outside a bin). If a part passes the
pick window end before it is gripped, the pick is abandoned and the part is marked missed. On reset,
a part still on the cup is placed in the Quarantine bin on the next run; a scheduled part that was not
gripped is marked missed.

## Bin selection (`F_SelectBin`, spec §7.2)

1. No valid vision result, confidence below `rConfidenceThreshold`, or an AI decision saying the
   identification is unreliable → **Quarantine**
2. Quality Scrap → **Scrap**; quality Rework → **Rework**
3. Otherwise the type bin of the detected class (`aClassToBin`)

Without a decision by `tDecisionDeadline` (2.5 s), the fallback rule applies (source *Fallback*).

## Alarms

| Id | Class | Effect |
|---|---|---|
| EStop, DoorOpen, BridgeLost, AxisGroupError, FollowingErrorFault, FeedbackStale | Critical | Abort |
| ConveyorError, VacuumNoGrip, VacuumLost, QueueOverflow | Error | Stop |
| FollowingErrorWarn, PartMissed, BinFull, VisionMissing, DecisionFallback, LowConfidence | Warning | none (BinFull: Suspend) |

PartMissed, VisionMissing, DecisionFallback and LowConfidence are one-shot events (`RaiseEvent`):
shown until acknowledged, never active, so they cannot block a reset. QueueOverflow clears itself
as soon as a record fits again.

## Simulation tests

Each file in `tests/plc/` is run with the MCP toolkit's `codesys_sim_test` against CODESYS's own
simulation (see `plc/scripts/README.md`).

| Spec | Cases | Covers |
|---|---|---|
| `types.json` | 1 | configuration defaults |
| `motion_smoke.json` | 1 | SoftMotion PTP move |
| `packml.json` | 8 | state machine, modes, held abort condition |
| `alarms.json` | 7 | latching, acknowledgement, classes, one-shot events |
| `equipment.json` | 6 | photo-eye, vacuum gripper, bin, safety monitor |
| `motion.json` | 5 | conveyor, robot PTP/linear, override, stop |
| `joint_monitor.json` | 5 | following error, stale feedback |
| `tracking.json` | 10 | capture, messages, fallback, missed parts, overflow |
| `pick.json` | 5 | tracked pick-and-place, vacuum loss, window end, abort and quarantine recovery |
| `cell.json` | 8 | **end-to-end cell (exit test)**, E-stop recovery, door, bin full, operator suspend, restart after vacuum loss, manual jog |
| `recipes.json` | 2 | Standard / HighSpeed |
| **Total** | **58** | |

Time-based cases use real-time waits; CODESYS's simulation slows down under CPU load, so the waits
have margin and expectations check steady states.
