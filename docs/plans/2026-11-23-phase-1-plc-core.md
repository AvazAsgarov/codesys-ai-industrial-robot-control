# Phase 1 — PLC Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CODESYS program that runs the whole sorting cell in CODESYS's own simulation: a 6-axis SoftMotion robot and conveyor, PackML states and modes, alarms, interlocks, part tracking, bin selection and a complete pick-and-place cycle from a moving belt. Every block is proven by simulation tests.

**Architecture:** Object-oriented Structured Text in the folder layout of spec §5.2. One control task (4 ms, also the SoftMotion bus cycle task) runs the cell and motion. `SoftMotion_PlanningTask` (freewheeling) serves the robotics planner. Everything the Python bridge will write later (sensors, joint feedback, vision and decision results) arrives through `GVL_Bridge`. In P1 those values are written by tests, and joint feedback is looped back from the setpoints.

**Tech Stack:** CODESYS V3.5 SP22 P4, SoftMotion 4.20 (SM3_Basic, SM3_Robotics, SM3_Transformation), CODESYS MCP toolkit (`codesys_sim_test`, `create_recipes`, `export_sources`), CODESYS IronPython scripting, pytest (test-spec validation only).

**Spec:** `docs/specs/2026-11-23-system-design.md` (§4.2, §4.3, §5, §7.2 bin selection, §6.3 quality labels). ADR 0004.

## Global Constraints

- All rules of `docs/conventions.md` §1: object prefixes, Hungarian variable prefixes, `{attribute 'qualified_only'}` on GVLs and enums, `{attribute 'strict'}` on enums, thin `PRG_*`, no magic numbers, FB header comment.
- SoftMotion units: **mm and degrees** (linear mm, mm/s; rotary °, °/s). Python converts to SI later.
- Verify every library FB with `get_signature` before first use. Confirmed so far: `SMC_GroupPower`, `MC_GroupEnable`, `MC_MoveDirectAbsolute` (dynamics via `VelFactor`/`AccFactor`/`JerkFactor`), `MC_MoveLinearAbsolute` (`Velocity`, `Acceleration`, `Deceleration`, `Jerk`), `MC_GroupReadActualPosition`, `MC_TrackConveyorBelt`.
- Every task ends with `compile` (check_all, deep) = **0 errors, 0 warnings**, its PLC test spec passing in `codesys_sim_test`, and `export_sources` → `plc/src/`.
- PLC test specs live in `tests/plc/<area>.json` (the `cases` argument of `codesys_sim_test`, verbatim). Every task adds its file **before** the code (RED: the case fails or the symbols don't exist).
- Commits: Conventional Commits, no AI attribution. Branch `phase/1-plc-core`, one PR, squash merge after CI is green.
- Demo licence: Control Win stops after ~2 h; the simulation is unaffected.

## Cell constants (fixed here; units mm / ° / mm/s)

| Name (`GVL_CellGeometry`, CONSTANT) | Value | Meaning |
|---|---|---|
| `ROBOT_D1`, `ROBOT_A1`, `ROBOT_A2`, `ROBOT_A3`, `ROBOT_D3`, `ROBOT_D4`, `ROBOT_D6` | 400, 50, 450, 50, 0, 450, 120 | `Kin_ArticulatedRobot_6DOF` parameters (d6 includes the suction tool). Also written into the axis-group config. |
| `BELT_ORIGIN` (`MC_COORD_REF`) | X −1500, Y −550, Z 0, A 0, B 0, C 0 | Belt frame; +X is the flow direction |
| `BELT_SURFACE_Z` | 0 | Belt top in the robot base frame |
| `PE1_X`, `PE2_X`, `PICK_WINDOW_END_X` (belt frame) | 300, 1050, 1750 | Camera/capture trigger, pick-window start and end (belt frame: 0 = infeed) |
| `HOME_ACS` (`SMC_POS_REF.a`) | 0, −30, 60, 0, 60, 0 | Home joint position |
| `BIN_DROP` array[E_Bin] of `MC_COORD_REF` | Z 250, A 0, B 180, C 0; Y +550; X = −500, −300, −100, +100, +300, +500 for TypeA, TypeB, TypeC, Rework, Scrap, Quarantine | Drop poses (tool pointing down) |

Process parameters (`GVL_Params`, retained, changed by recipes): `lrBeltSpeed` 100, `lrApproachHeight` 80, `lrPickDepth` 5, `lrLinVelocity` 500, `lrLinAccel` 2000, `lrLinJerk` 20000, `lrPtpVelFactor` 0.5, `rConfidenceThreshold` 0.6, `tDecisionDeadline` T#2.5S, `tVacuumTimeout` T#500MS, `lrFollowErrWarn` 2.0 (°), `lrFollowErrFault` 5.0 (°), `tFeedbackTimeout` T#500MS, `aClassToBin` [0..2] = TypeA, TypeB, TypeC.

## Review Focus

1. **Part reaches the end of the pick window before the robot gets to it.** Expected: it is marked `Missed`, a `PartMissed` warning is raised, and the cycle continues with the next part. It must not chase the part out of reach. Test `missed_part_is_skipped` (Task 8).
2. **No decision by the deadline / vision result missing.** Expected: the fallback bin rule applies (quarantine if vision is missing; class bin otherwise) and `eDecisionSource = Fallback`. Tests `deadline_uses_fallback`, `no_vision_goes_to_quarantine` (Task 8).
3. **E-stop or door opened in the middle of a move.** Expected: the group stops immediately, PackML goes to Aborting→Aborted, the vacuum stays **on** (no dropped part), and no motion happens until Clear and Reset. Test `estop_during_transfer_keeps_vacuum` (Task 10).
4. **Vacuum lost while carrying a part.** Expected: `VacuumLost` error → Stopping→Stopped, and the part is recorded as dropped. Test `vacuum_lost_in_transfer_stops_cell` (Task 9).
5. **Duplicate or stale bridge messages** (the same sequence number written twice; a result for an unknown part id). Expected: ignored, no double counting. Tests `duplicate_result_ignored`, `unknown_part_result_ignored` (Task 8).

---

### Task 1: SoftMotion base project (reproducible) and task model

**Files:**
- Create: `plc/scripts/build_softmotion_base.py` (CODESYS IronPython), `plc/scripts/templates/AxisGroup_Robot.export`
- Replace: `plc/RobotCell.project`
- Modify: `plc/scripts/README.md`, `docs/specs/2026-11-23-system-design.md` §5.1, `.claude/skills/softmotion-robotics/SKILL.md`
- Test: `tests/plc/motion_smoke.json`, `tests/unit/test_plc_test_specs.py`

**Interfaces:**
- Produces: devices `Axis_J1…Axis_J6`, `Axis_Conveyor` (`SM_Drive_Virtual`) under `SoftMotion General Axis Pool`; axis group `AxisGroup_Robot` (`TRAFO.Kin_ArticulatedRobot_6DOF`, params from *Cell constants*, mapping J1…J6, no additional axes, planning task `SoftMotion_PlanningTask`); tasks `MainTask` cyclic **4 ms** prio 1 (SoftMotion bus cycle task) → `PRG_Main`; `CommTask` 50 ms prio 10 → `PRG_Comm`; `SoftMotion_PlanningTask` freewheeling 2 ms prio 15; `TestTask` cyclic 10 ms prio 20 → `PRG_Tests`. P0 objects recreated: folders, `GVL_Constants`, `PRG_Main` (with `sProjectVersion`), `PRG_Comm`. `PRG_Motion`/`MotionTask` are removed (one control task, see Ruling).
- Produces: `tests/plc/*.json` format = `{"cases": [ {"name": str, "steps": [ {write|force|unforce|cycles|waitMs|expect} ]} ]}`.

- [ ] **Step 1: Test-spec validator (pytest, RED).** `tests/unit/test_plc_test_specs.py::test_every_plc_spec_is_well_formed` loads every `tests/plc/*.json`, asserts a non-empty `cases` list, unique case names, and that each step has only the keys `write`, `force`, `unforce`, `cycles`, `waitMs`, `expect`. `test_plc_specs_exist` asserts at least one file. Run → FAIL (no files).
- [ ] **Step 2: Write `tests/plc/motion_smoke.json`** with case `ptp_move_reaches_target`: write `PRG_TestMotionSmoke.xGo := TRUE`, wait 4000 ms, expect `PRG_TestMotionSmoke.fbMove.Done = TRUE`, `…lrJ1 = 30 (tolerance 0.01)`, `…lrJ2 = -20 (tolerance 0.01)`. pytest → PASS; the sim test is RED (no project yet).
- [ ] **Step 3: Write `build_softmotion_base.py`** from the probe that was proven in research: copy `…\CODESYS SoftMotion\Examples\Tutorial\Robotics_Jogging.project`, open with `VersionUpdateFlags.UpdateAll | SilentMode`, update the device to Control Win V3 x64 3.5.22.40 and the pool/drives to the newest versions, remove the example's application objects, root objects and root libraries `#SM3_Depictor`/`#DepictorBase`, remove `AddAxis_*` drives, rename `Drive_A1…A6` → `Axis_J1…J6`, add `Axis_Conveyor`, import `templates/AxisGroup_Robot.export` (kinematics parameters substituted from the *Cell constants*), `save_as` the output path given by `ROBOTCELL_BASE_OUT`. The template is the example's axis-group export, re-targeted and with an empty `AdditionalAxisMapping`.
- [ ] **Step 4: Build and finish the base with the MCP tool:**
  - Remove the visualization and CNC library references left by the example (names with `#`).
  - Recreate the P0 folders and objects.
  - Configure the tasks as in *Interfaces*.
  - Set the axis pool's bus cycle task to `MainTask` (`device_parameters` / `configure_device`).
  - Set drive software limits and maximums: J1 ±170°, J2 −90…+150°, J3 −120…+150°, J4 ±180°, J5 −120…+120°, J6 ±360°; v max J1–J3 180°/s, J4–J6 360°/s; a max 1000°/s². Conveyor: linear mm, v max 400 mm/s.
  - Add `PRG_TestMotionSmoke` in `Tests` (power, enable, `MC_MoveDirectAbsolute` to 30/−20/40/0/45/0, `VelFactor` 0.5; outputs `lrJ1`, `lrJ2`) and `PRG_Tests` calling it.
- [ ] **Step 5: Verify:** compile 0/0. `codesys_sim_start run` → `codesys_sim_test` with `motion_smoke.json` → **1/1 pass**. `codesys_sim_stop`.
- [ ] **Step 6:** Replace `plc/RobotCell.project`, `export_sources`, re-export (0 files changed). Update §5.1 of the spec (task table) and the softmotion skill (base build, units, confirmed FBs). Commit `feat(plc): rebuild project on a SoftMotion base with a 6-axis axis group`.

---

### Task 2: Types, configuration and GVLs

**Files (all in the CODESYS project; exported under `plc/src/`):**
- `Types/`:
  - `E_PackMLState`: Undefined=0, Clearing=1, Stopped=2, Starting=3, Idle=4, Suspended=5, Execute=6, Stopping=7, Aborting=8, Aborted=9, Holding=10, Held=11, Unholding=12, Suspending=13, Unsuspending=14, Resetting=15, Completing=16, Complete=17 (ISA-TR88 numbering).
  - `E_PackMLMode`: Production=1, Maintenance=2, Manual=3.
  - `E_PackMLCommand`: None=0, Reset=1, Start=2, Stop=3, Hold=4, Unhold=5, Suspend=6, Unsuspend=7, Abort=8, Clear=9, Complete=10.
  - `E_AlarmClass`: Info, Warning, Error, Critical.
  - `E_AlarmId`: None, EStop, DoorOpen, BridgeLost, AxisGroupError, ConveyorError, FollowingErrorWarn, FollowingErrorFault, FeedbackStale, VacuumNoGrip, VacuumLost, PartMissed, BinFull, VisionMissing, DecisionFallback, LowConfidence, QueueOverflow, _Count.
  - `E_Bin`: TypeA, TypeB, TypeC, Rework, Scrap, Quarantine.
  - `E_Quality`: Unknown, Ok, Rework, Scrap.
  - `E_DecisionSource`: None, Ai, Fallback.
  - `E_PartState`: Free, Captured, Identified, Decided, Scheduled, Picked, Placed, Missed, Dropped.
  - `ST_PartRecord`: `udiPartId`, `lrBeltPosAtCapture`, `xVisionValid`, `usiClass`, `rConfidence`, `lrX`, `lrY`, `lrTheta` (belt frame mm/°), `eQuality`, `rQualityProb`, `xIdentReliable`, `eDecisionSource`, `eTargetBin`, `eState`, `tCaptured : TIME`.
  - `ST_Alarm`: `eClass`, `xActive`, `xAcked`, `tRaised : TIME`, `sText : STRING(80)`.
- `Config/`: `GVL_CellGeometry` (CONSTANT, the *Cell constants*), `GVL_Params` (`VAR_GLOBAL RETAIN`, the *Process parameters*), `GVL_Config` (`xFeedbackLoopback : BOOL := TRUE` for P1, `MAX_PARTS : UINT := 32`), `GVL_AlarmDefs` (CONSTANT `aDefs : ARRAY[E_AlarmId] OF ST_Alarm`, class + text per alarm; EStop/DoorOpen/BridgeLost/AxisGroupError/FollowingErrorFault/FeedbackStale = Critical; ConveyorError/VacuumNoGrip/VacuumLost/BinFull/QueueOverflow = Error; the rest = Warning).
- `Comm/`:
  - `GVL_Bridge` inputs: `xHeartbeat`, `aJointPosFb : ARRAY[1..6] OF LREAL`, `aJointTorqueFb : ARRAY[1..6] OF LREAL`, `udiFeedbackSeq`, `xPE1`, `xPE2`, `xVacuumOk`, `axBinFull : ARRAY[E_Bin] OF BOOL`, `xDoorClosed`, `xEStopOk`, `stVision : ST_VisionMsg`, `stDecision : ST_DecisionMsg`.
  - `GVL_Bridge` outputs: `aJointPosSp : ARRAY[1..6] OF LREAL`, `lrBeltPos`, `lrBeltVel`, `xVacuumOn`, `stCapture : ST_CaptureMsg`, `eState`, `eMode`.
  - `ST_VisionMsg` (`udiSeq`, `udiPartId`, `xValid`, `usiClass`, `rConfidence`, `lrX`, `lrY`, `lrTheta`), `ST_DecisionMsg` (`udiSeq`, `udiPartId`, `eQuality`, `rQualityProb`, `xIdentReliable`), `ST_CaptureMsg` (`udiSeq`, `udiPartId`, `lrBeltPos`).
  - `GVL_Hmi`: `eCommand`, `eModeRequest`, `xAlarmAck`, `axJogPlus`/`axJogMinus : ARRAY[1..6] OF BOOL`, `rOverride : REAL := 1.0`.
- Test: `tests/plc/types.json`

- [ ] **Step 1: RED:** `types.json` case `defaults_are_sane` expects `GVL_Params.lrBeltSpeed = 100`, `GVL_Config.xFeedbackLoopback = TRUE`, `PRG_TestTypes.eClassBin0 = 'E_Bin.TypeA'`, and `PRG_TestTypes.eFaultClass = 'E_AlarmClass.Critical'` (reads `GVL_AlarmDefs.aDefs[E_AlarmId.EStop].eClass`). Run → fails (symbols unknown).
- [ ] **Step 2:** Create the objects above, plus `PRG_TestTypes` (two outputs copied from the GVLs).
- [ ] **Step 3:** compile 0/0; `codesys_sim_test types.json` → pass. Export, commit `feat(plc): add types, configuration and bridge/HMI variable lists`.

---

### Task 3: PackML state machine

**Files:** `Framework/FB_PackMLStateMachine`; `Tests/PRG_TestPackML`; `tests/plc/packml.json`

**Interfaces:**
- Produces: `FB_PackMLStateMachine` with VAR_INPUT `eCommand : E_PackMLCommand`, `eModeRequest : E_PackMLMode`, `xStateComplete : BOOL` (unit finished the current acting state), `xAbortRequest : BOOL` (critical condition, any state except Aborting/Aborted), `xStopRequest : BOOL` (error condition), `xSuspendRequest : BOOL`, `xUnsuspendRequest : BOOL`. VAR_OUTPUT `eState : E_PackMLState := Stopped`, `eMode : E_PackMLMode := Production`, `xStateChanged : BOOL` (one cycle), `tInState : TIME`. Initial state `Stopped`.
- Transitions follow ISA-TR88.00.02. Acting states (Starting, Stopping, Aborting, Clearing, Resetting, Holding, Unholding, Suspending, Unsuspending, Completing) leave on `xStateComplete`. Mode changes are accepted only in Stopped, Idle, Aborted.

- [ ] **Step 1: RED:** `packml.json` cases (each writes commands via `PRG_TestPackML.fbSm.*`, runs 2 cycles, expects state):
  - `reset_start_reaches_execute`: Stopped –Reset→ Resetting –complete→ Idle –Start→ Starting –complete→ Execute
  - `stop_from_execute`: → Stopping –complete→ Stopped
  - `abort_from_any_state`: xAbortRequest in Execute → Aborting –complete→ Aborted; Reset ignored in Aborted; Clear → Clearing –complete→ Stopped
  - `hold_unhold`: Execute –Hold→ Holding → Held –Unhold→ Unholding → Execute
  - `suspend_on_starvation`: xSuspendRequest in Execute → Suspending → Suspended; xUnsuspendRequest → Unsuspending → Execute
  - `mode_change_only_when_allowed`: eModeRequest Manual in Execute → eMode stays Production; in Stopped → Manual
  - `invalid_command_ignored`: Start while Stopped stays Stopped
- [ ] **Step 2:** Implement (CASE on state; `R_TRIG` on command changes so a held command acts once; `xStateChanged` from a previous-state compare).
- [ ] **Step 3:** compile 0/0; tests 7/7. Export, commit `feat(plc): add PackML state machine`.

---

### Task 4: Alarm handler

**Files:** `Interfaces/I_AlarmSink`; `Framework/FB_AlarmHandler`; `Tests/PRG_TestAlarms`; `tests/plc/alarms.json`

**Interfaces:**
- Produces: `I_AlarmSink` with `METHOD Raise(eId : E_AlarmId)` and `METHOD Clear(eId : E_AlarmId)`. `FB_AlarmHandler IMPLEMENTS I_AlarmSink` with `METHOD AcknowledgeAll()`; outputs `xCriticalActive`, `xErrorActive`, `xWarningActive`, `uiActiveCount : UINT`, `eNewest : E_AlarmId`; property `Alarms : ARRAY[E_AlarmId] OF ST_Alarm` (get). Semantics: Raise of an active alarm doesn't re-timestamp. Clear while unacked keeps it listed (inactive, unacked) until AcknowledgeAll. Class flags count **active OR unacked** alarms, so a fault needs acknowledgement (ISA-18.2 latching).

- [ ] **Step 1: RED:** cases `raise_sets_class_flag` (EStop → `xCriticalActive`), `clear_without_ack_keeps_flag`, `ack_after_clear_resets`, `raise_twice_counts_once`, `warning_does_not_set_error`.
- [ ] **Step 2:** Implement. Classes and texts come from `GVL_AlarmDefs`.
- [ ] **Step 3:** compile 0/0; tests 5/5. Export, commit `feat(plc): add latching alarm handler`.

---

### Task 5: Simple equipment: photo-eye, vacuum gripper, bin, safety monitor

**Files:** `Interfaces/I_Equipment`; `Equipment/FB_PhotoEye`, `FB_VacuumGripper`, `FB_Bin`, `FB_SafetyMonitor`; `Tests/PRG_TestEquipment`; `tests/plc/equipment.json`

**Interfaces:**
- `I_Equipment`: `METHOD Reset : BOOL`, `PROPERTY HasError : BOOL` (get), `PROPERTY ErrorId : E_AlarmId` (get).
- `FB_PhotoEye(xRaw : BOOL, tDebounce : TIME := T#10MS)` → `xBlocked`, `xRising` (one cycle).
- `FB_VacuumGripper IMPLEMENTS I_Equipment`: in `xCmdVacuum`, `xVacuumOk`, `tGripTimeout`, `itfAlarms : I_AlarmSink`; out `xValveOn`, `xHolding`. Raises `VacuumNoGrip` if not OK within the timeout after the command; raises `VacuumLost` if OK→NOT OK while commanded.
- `FB_Bin`: in `eBin`, `xFullSensor`, `xPlaced` (rising edge = +1); out `uiCount`, `xFull`; `METHOD Empty()`.
- `FB_SafetyMonitor`: in `xEStopOk`, `xDoorClosed`, `eMode`, `xResetCmd`, `itfAlarms`; out `xSafeToMove`, `xReducedSpeed`. The E-stop latches until `xEStopOk` AND `xResetCmd`. Door open in Production/Maintenance → not safe (raises `DoorOpen`). Door open in Manual → safe with `xReducedSpeed`.
- [ ] **Step 1: RED** cases: `photoeye_debounce` (5 ms pulse ignored, 20 ms → xRising once), `vacuum_no_grip_timeout`, `vacuum_lost_raises`, `bin_counts_rising_edges`, `estop_latches_until_reset`, `door_open_manual_reduced_speed`.
- [ ] **Step 2:** Implement. **Step 3:** compile 0/0; 6/6; export; commit `feat(plc): add photo-eye, vacuum gripper, bin and safety monitor`.

---

### Task 6: Motion wrappers: conveyor and robot

**Files:** `Equipment/FB_Conveyor`, `FB_Robot`; `Tests/PRG_TestMotion`; `tests/plc/motion.json`

**Interfaces:**
- `FB_Conveyor IMPLEMENTS I_Equipment` (VAR_IN_OUT `Axis : AXIS_REF_SM3`): in `xEnable`, `lrVelocity` (mm/s), `xRun`; out `xPowered`, `lrPosition` (mm), `lrActVelocity`. Uses `MC_Power`, `MC_MoveVelocity`, `MC_Halt`, `MC_ReadActualPosition`. Error → `ConveyorError`.
- `FB_Robot IMPLEMENTS I_Equipment` (VAR_IN_OUT `AxisGroup : AXIS_GROUP_REF_SM3`): in `xEnable`, `rOverride`, `itfAlarms`. Methods:
  - `MovePtpAcs(stTarget : SMC_POS_REF) : BOOL` and `MoveLinear(stTarget : SMC_POS_REF, eCs : SMC_COORD_SYSTEM) : BOOL`. Both return TRUE when Done; start on the first call and continue while called.
  - `Halt()`, `Stop()`, `ResetGroup()`.
  - Properties `IsReady`, `IsMoving`, `ActPosAcs`, `ActPosMcs`, `SetPosAcs : ARRAY[1..6] OF LREAL` (for the joint monitor and the bridge).
  - Internals: `SMC_GroupPower`, `MC_GroupEnable`, `MC_GroupReset`, `MC_GroupHalt`, `MC_GroupStop`, `MC_GroupSetOverride`, `MC_MoveDirectAbsolute`, `MC_MoveLinearAbsolute`, `MC_GroupReadActualPosition` (ACS and MCS), `SMC_GroupReadSetPosition`; verify each with `get_signature`.
  - Error → `AxisGroupError`.
- [ ] **Step 1: RED** cases: `conveyor_runs_at_speed` (100 mm/s for 2 s → position ≥ 180 and ≤ 220), `robot_ptp_home` (reaches `HOME_ACS` ±0.01°), `robot_linear_mcs` (from home, linear to the TCP + (0, 0, −50) → Done, Z changes by −50 ±0.1), `robot_override_half_is_slower` (same PTP takes longer at override 0.5, measured with a cycle counter output), `robot_stop_cancels_move`.
- [ ] **Step 2:** Implement. **Step 3:** compile 0/0; 5/5; export; commit `feat(plc): add conveyor and robot motion wrappers`.

---

### Task 7: Joint supervision

**Files:** `Equipment/FB_JointMonitor`; `Tests/PRG_TestJointMonitor`; `tests/plc/joint_monitor.json`

**Interfaces:**
- `FB_JointMonitor`: in `aSetpoint : ARRAY[1..6] OF LREAL`, `aFeedback : ARRAY[1..6] OF LREAL`, `aTorque : ARRAY[1..6] OF LREAL`, `udiFeedbackSeq : UDINT`, `xLoopback : BOOL`, `xActive : BOOL`, `itfAlarms`; out `aFollowingError : ARRAY[1..6] OF LREAL`, `iWorstJoint : INT`, `xWarn`, `xFault`. Loopback means feedback := setpoint and staleness is not checked. Otherwise: |sp − fb| > `lrFollowErrWarn` → `FollowingErrorWarn`; > `lrFollowErrFault` → `FollowingErrorFault`; `udiFeedbackSeq` unchanged for `tFeedbackTimeout` while active → `FeedbackStale`.
- [ ] **Step 1: RED** cases: `loopback_never_faults`, `warn_threshold`, `fault_threshold_and_worst_joint`, `stale_feedback_faults`, `inactive_no_stale_check`.
- [ ] **Step 2:** Implement. **Step 3:** compile 0/0; 5/5; export; commit `feat(plc): add joint following-error and feedback supervision`.

---

### Task 8: Part tracking, intake and bin selection

**Files:** `Framework/FB_PartQueue`; `Equipment/FB_CameraTrigger`; `Process/FB_PartTracker`, `F_SelectBin`; `Comm/FB_MessageIntake`; `Tests/PRG_TestTracking`; `tests/plc/tracking.json`

**Interfaces:**
- `FB_PartQueue`: fixed array `[1..GVL_Config.MAX_PARTS] OF ST_PartRecord`. Methods `Add(stRec) : BOOL` (FALSE when full → `QueueOverflow`), `FindIndex(udiPartId) : UINT` (0 = none), `Get(uiIdx) : ST_PartRecord`, `Put(uiIdx, stRec)`, `Release(uiIdx)`; property `Count`.
- `FB_CameraTrigger`: in `xPE1Rising`, `lrBeltPos`; out `stCapture : ST_CaptureMsg` (`udiSeq` increments; `udiPartId` increments from 1), `xNewPart`, `udiNewPartId`.
- `FB_MessageIntake`: in `stVision`, `stDecision`; out `xVisionNew`, `xDecisionNew` (true one cycle when `udiSeq` changed), so duplicates are ignored.
- `F_SelectBin(stRec : ST_PartRecord, rConfThreshold : REAL, aClassToBin : ARRAY[0..2] OF E_Bin) : E_Bin`, implementing spec §7.2:
  1. Not `xVisionValid`, or `NOT xIdentReliable` with `eDecisionSource = Ai`, or `rConfidence < threshold` → Quarantine.
  2. Otherwise `eQuality = Scrap` → Scrap; `eQuality = Rework` → Rework.
  3. Otherwise `aClassToBin[usiClass]`.
- `FB_PartTracker`: owns `FB_PartQueue`, the camera trigger and the intake. In: `lrBeltPos`, `xPE1Rising`, `stVision`, `stDecision`, `itfAlarms`. Behaviour:
  - It applies results only to known part ids.
  - At `tDecisionDeadline` after capture without a decision, it sets `eDecisionSource = Fallback` and `eQuality = Unknown`, raises the `DecisionFallback` warning, and fills `eTargetBin` via `F_SelectBin`.
  - Its current belt X for a part is `lrX + (lrBeltPos − lrBeltPosAtCapture)`.
  - When that passes `PICK_WINDOW_END_X` it marks the part `Missed` and raises `PartMissed`.
  - It provides `METHOD NextPickable(lrMinX, lrMaxX) : UINT`, returning the decided part that is furthest downstream in the window, and `METHOD SetState(uiIdx, eState)`.
- [ ] **Step 1: RED** cases:
  - `capture_creates_record`
  - `vision_then_decision_sets_bin`: class 1, quality Ok, reliable, confidence 0.9 → TypeB
  - `scrap_goes_to_scrap`
  - `low_confidence_quarantine`
  - `no_vision_goes_to_quarantine`
  - `deadline_uses_fallback`: class 2, no decision for 2.6 s → TypeC, source Fallback
  - `duplicate_result_ignored`: the same `udiSeq` twice with a different class keeps the first
  - `unknown_part_result_ignored`
  - `missed_part_is_skipped`: belt moves the part past the window end → Missed, `NextPickable` = 0
  - `queue_overflow_alarm`
- [ ] **Step 2:** Implement. **Step 3:** compile 0/0; 10/10; export; commit `feat(plc): add part tracking, message intake and bin selection`.

---

### Task 9: Pick-and-place sequence with conveyor tracking

**Files:** `Process/FB_PickSequence`; `Tests/PRG_TestPick`; `tests/plc/pick.json`

**Interfaces:**
- `FB_PickSequence` (VAR_IN_OUT `AxisGroup`, `Conveyor : AXIS_REF_SM3`). Uses `FB_Robot` (by reference via `FB_init`: `itfRobot`-free; it receives `REFERENCE TO FB_Robot`), `FB_VacuumGripper`, `FB_PartTracker` (reference).
  - In: `xRun` (FALSE finishes the current part then idles), `xAbort` (immediate stop, vacuum kept).
  - Out: `eStep : E_PickStep`, `xIdleAtHome`, `xBusy`, `udiPicked`, `udiPlaced`, `eLastBin`.
- `E_PickStep`: Idle, MoveHome, WaitPart, StartTracking, Approach, Descend, Grip, Lift, MoveToBin, Release, Retract, Done, Error.
- Sequence (all poses in mm/°; tool pointing down = A 0, B 180, C part θ):
  1. `MC_TrackConveyorBelt` (`ConveyorBeltOrigin` = `BELT_ORIGIN`, `InitialObjectPosition` = the part's belt-frame X/Y/θ at capture, `CoordSystem` = PCS_1).
  2. Linear move in PCS_1 to the part + Z `lrApproachHeight`, then down to Z −`lrPickDepth`.
  3. Vacuum on; wait `xHolding` (timeout → error path).
  4. Linear up `lrApproachHeight` in PCS_1.
  5. PTP to `BIN_DROP[eTargetBin]` in MCS, vacuum off, wait 200 ms.
  6. Linear retract +100 mm Z; mark the part Placed and tell the bin.
  7. Continue with the next part, or go home.
- [ ] **Step 1: RED** cases (force `GVL_Bridge.xVacuumOk` with a short delay after the valve opens; belt running at 100 mm/s):
  - `single_part_placed_in_target_bin`: a decided TypeB part enters the window → `udiPlaced = 1`, `eLastBin = TypeB`, robot back at home ±0.5°.
  - `vacuum_lost_in_transfer_stops_cell`: unforce `xVacuumOk` during MoveToBin → `eStep = Error`, part state Dropped, `VacuumLost` active.
  - `run_false_finishes_then_idles`
  - `abort_keeps_vacuum`: `xAbort` during Lift → group stopped, `xValveOn` stays TRUE.
- [ ] **Step 2:** Implement. **Step 3:** compile 0/0; 4/4; export; commit `feat(plc): add tracked pick-and-place sequence`.

---

### Task 10: Sorting cell unit, interlocks, watchdog and program wiring

**Files:** `Process/FB_SortingCell`; `Comm/FB_BridgeWatchdog`; `Programs/PRG_Main` (instantiation and call only), `PRG_Comm`; `Tests/PRG_TestCell`; `tests/plc/cell.json`

**Interfaces:**
- `FB_BridgeWatchdog`: in `xHeartbeat`, `xEnable`, `tTimeout := T#500MS`, `itfAlarms`; raises `BridgeLost` when the heartbeat has not toggled for `tTimeout`. Disabled while `GVL_Config.xFeedbackLoopback` (P1).
- `FB_SortingCell`: owns `FB_PackMLStateMachine`, `FB_AlarmHandler`, `FB_SafetyMonitor`, `FB_Conveyor`, `FB_Robot`, `FB_JointMonitor`, `FB_PartTracker`, `FB_PickSequence`, six `FB_Bin`, two `FB_PhotoEye`, `FB_BridgeWatchdog`. Inputs come from `GVL_Hmi`/`GVL_Bridge`; outputs are written to `GVL_Bridge` (setpoints, belt, vacuum, capture, state, mode).
  - **State actions:**
    - Resetting: reset group and alarms (ack); complete when no critical alarm.
    - Starting: power the robot, move home, start the conveyor at `lrBeltSpeed`; complete when home and belt at speed.
    - Execute: `PickSequence.xRun`.
    - Stopping: `xRun := FALSE`; complete when `xIdleAtHome`; conveyor halted.
    - Holding: as Stopping but keep power.
    - Suspending: when the queue is empty for 10 s or the target bin is full; Unsuspending when parts/bins are available.
    - Aborting: `xAbort`, group stop, conveyor stop, keep vacuum; complete when the group is stopped.
    - Clearing: reset the group.
  - **Interlocks:** a critical alarm or `NOT xSafeToMove` → `xAbortRequest`; an Error-class alarm → `xStopRequest`.
  - **Manual mode:** jog via `SMC_GroupJog2` from `GVL_Hmi.axJogPlus`/`axJogMinus`, at 25 % override when `xReducedSpeed`.
- [ ] **Step 1: RED** cases:
  - `full_cycle_three_parts`: Reset, Start; inject three parts (PE1 pulses 1.5 s apart, vision and decision messages for classes 0/1 with quality Ok and one Scrap) → bins TypeA = 1, TypeB = 1, Scrap = 1, state Execute, no active Error/Critical. **This is the P1 exit test.**
  - `estop_during_transfer_keeps_vacuum`: E-stop while a part is held → Aborted, `GVL_Bridge.xVacuumOn = TRUE`, robot not moving; Clear + Reset with E-stop restored → Stopped/Idle.
  - `door_open_in_production_aborts`
  - `bin_full_suspends`: TypeA bin full sensor → Suspended after the current part; clear → Execute.
  - `stop_completes_at_home`
  - `manual_jog_only_in_manual`: jog J1+ in Production → no motion; in Manual → J1 increases.
- [ ] **Step 2:** Implement. **Step 3:** compile 0/0; 6/6, plus all earlier spec files re-run (regression). Export; commit `feat(plc): add sorting cell unit with PackML, interlocks and watchdog`.

---

### Task 11: Recipes

**Files:** generated `ST_Recipe_Cell`, `GVL_Recipe_Cell`, `PRG_Recipe_Cell` (via `create_recipes`); `tests/plc/recipes.json`

- [ ] **Step 1: RED** cases: `apply_highspeed` (write `PRG_Recipe_Cell.iApply := 2` → `GVL_Params.lrBeltSpeed = 200`, `lrLinVelocity = 800`), `apply_standard_restores` (→ 100, 500).
- [ ] **Step 2:** `create_recipes name=Cell`, variables = all `GVL_Params` entries; recipes **Standard** (the defaults above) and **HighSpeed** (`lrBeltSpeed` 200, `lrLinVelocity` 800, `lrLinAccel` 3000, `lrPtpVelFactor` 0.8, the rest as Standard). Make sure `PRG_Recipe_Cell` is called by `MainTask`.
- [ ] **Step 3:** compile 0/0; 2/2; full regression; export; commit `feat(plc): add Standard and HighSpeed recipes`.

---

### Task 12: Documentation and phase close

**Files:** `docs/adr/0007-single-control-task-and-st-alarms.md`; `docs/architecture/plc.md` (object map, state table, alarm table, test inventory); `.claude/skills/codesys-st-conventions/SKILL.md`, `softmotion-robotics/SKILL.md` (P1 extensions: base build, units, FB patterns, test-spec workflow); `README.md` (status line); `CHANGELOG.md` (`[0.2.0]`); `docs/specs/…` §5.4/§5.5 notes.

- [ ] **Step 1:** ADR 0007 records two decisions. First, a single 4 ms control task instead of separate 2 ms/10 ms tasks: Control Win isn't real-time, and calling SoftMotion FBs from two tasks invites races. Second, alarms are latched in ST (`FB_AlarmHandler`) in P1, and CODESYS AlarmManager integration comes with the HMI in P5. Recipes are generated ST (`create_recipes`) rather than a Recipe Manager object.
- [ ] **Step 2:** `docs/architecture/plc.md` with the tables generated from `GVL_AlarmDefs` and `tests/plc/*.json` (case count per file).
- [ ] **Step 3:** Full verification: `uv run pytest`, `uv run pre-commit run --all-files`, compile 0/0, every `tests/plc/*.json` passes; export stable.
- [ ] **Step 4:** Commit `docs: document PLC core, ADR 0007, skills for phase 1`; push; PR "Phase 1: PLC core"; CI green; squash merge; tag `v0.2.0`.
