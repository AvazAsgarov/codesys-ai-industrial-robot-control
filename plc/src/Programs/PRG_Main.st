(*
    PRG_Main
    Purpose : Cell logic entry point: PackML state machine, equipment logic,
              part tracking and alarms (instantiated from Phase 1 on).
    Task    : MainTask, cyclic 10 ms
    Rule    : thin program - only instantiation and calls, no logic.
*)
PROGRAM PRG_Main
VAR
    sProjectVersion : STRING := GVL_Constants.PROJECT_VERSION;  // diagnostics: firmware/project version visible online and via OPC UA
END_VAR

// Intentionally empty in Phase 0.
