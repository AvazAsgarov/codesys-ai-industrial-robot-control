# 10. Operator HMI: native CODESYS visualization generated from screen descriptions

- **Status:** Accepted
- **Date:** 2026-11-25

## Context

The operator HMI (spec §9) must run with the application (TargetVisu and WebVisu), follow ISA-101
(neutral greys, colour only for abnormal states and alarms) and ISA-18.2 alarm priorities, and
be testable. The course grades the PLC code, so the HMI's behaviour should live in Structured
Text that the simulation tests can reach, not in element properties of the visualization.

## Decision

- **Two thin PLC blocks carry the HMI's logic.** `FB_HmiPanel` turns the panel's buttons
  (`GVL_HmiPanel`, rising edge, cleared after one cycle, Abort > Stop > Clear > Reset > Suspend >
  Unsuspend > Start) and the mode selector (applied only when it changes) into the cell's commands
  (`GVL_Hmi`). `FB_HmiView` prepares everything the screens show (`GVL_HmiView`: state, mode and
  pick-step texts, state groups, alarm rows, equipment signals, counters). The screens contain no
  logic; `tests/plc/hmi.json` drives the panel variables in simulation.
- **Screens are described, then generated.** `hmi/build_screens.py` writes the screen
  descriptions (Overview, Robot, Alarms; 1920x1080, 12x8 grid, accent `#2F5D8A`), the CODESYS
  HMI tool stores them (`plc/RobotCell.hmi.json`) and exports them as native visualizations
  `Visu_*` with a generated `PRG_HMI_*` each in `VISU_TASK`. Generated objects are not edited by
  hand: change the description and export again.
- **Alarm rows are lamps on `GVL_HmiView.axAlarm[]`** (lit while the alarm is active or
  unacknowledged, with the P1/P2/P3 prefix), plus a "conditions present" list from
  `axAlarmActive[]`. `FB_AlarmHandler` stays the single alarm source; acknowledge goes through the
  panel. The tool's rows on CODESYS alarm management were tried and dropped: their generated code
  does not build on SP22 Patch 4 (`__Alm__GVL.g_inst` is not generated).
- **The PLC protects the machine, not the screen.** Mode changes are accepted only in Stopped,
  Idle or Aborted; jog acts only in Manual mode and Execute; Clear only leaves Aborted once the
  condition is gone; Abort must be reachable by everyone. The screens can gate Clear, Abort, jog
  and the speed override to the visualization's Maintenance user group (`GATE_BY_ROLE` in
  `hmi/build_screens.py`), but that needs user accounts in the Visualization Manager; the demo
  build has none, so the gates are off (since Phase 6). This replaces the PIN login in ST that
  the Phase 5 plan proposed.

## Consequences

- No time stamps or alarm history on the screens (the PLC keeps the newest alarm and the
  bridge logs every state change); a later phase can add an ST alarm history.
- The mode selector shows the requested mode; the actual mode is in the top bar (`sMode`).
- The jog buttons write `GVL_Hmi.axJogPlus/Minus` while pressed; `FB_SortingCell` only jogs in
  Manual mode and Execute (`manual_jog_only_in_manual`), and `GVL_HmiView.xJogPermitted` shows it.
