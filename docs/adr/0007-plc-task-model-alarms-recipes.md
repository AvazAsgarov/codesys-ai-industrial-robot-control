# 7. PLC task model, alarm handling and recipes

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

The design (spec §5.1) planned a 2 ms `MotionTask` for SoftMotion and a 10 ms `MainTask` for
the cell logic, CODESYS AlarmManager for alarms and the Recipe Manager for recipes. Phase 1
showed:

- CODESYS Control Win is not hard real-time, and SoftMotion function blocks belong in the bus
  cycle task. Splitting cell logic and motion over two tasks means commanding the axis group from
  one task while it is processed in another, which invites race conditions for little benefit in a
  soft-PLC simulation.
- The CODESYS MCP toolkit can create native alarms only together with an HMI (Phase 5), and
  generates recipes as Structured Text.

## Decision

1. **One control task.** `MainTask` (cyclic 4 ms, priority 1) is the SoftMotion bus cycle task
   and runs the whole cell: PackML, equipment, motion, part tracking, alarms. The robotics planner
   runs in `SoftMotion_PlanningTask` (freewheeling, priority 15). `CommTask` (50 ms) is reserved
   for OPC UA consistency in Phase 2.
2. **Alarms in Structured Text.** `FB_AlarmHandler` keeps a latching alarm list (ISA-18.2 style:
   an alarm leaves the list only when its condition is gone and it is acknowledged). Classes map to
   PackML: Critical → Abort, Error → Stop, Warning → no state change (BinFull suspends the unit).
   Native CODESYS AlarmManager alarms are generated from this list with the HMI in Phase 5.
3. **Recipes as generated ST.** `create_recipes` generates `ST_Recipe_Cell`, `GVL_Recipe_Cell`
   (RETAIN) and `PRG_Recipe_Cell`; recipes *Standard* and *HighSpeed* write `GVL_Params`.

## Consequences

- All motion is deterministic within one task; no cross-task data exchange inside the cell.
- Alarm behaviour is fully covered by simulation tests (`tests/plc/alarms.json`, `cell.json`).
- Phase 5 adds the AlarmManager mapping and the recipe screen; the ST alarm list stays the source
  of truth.
