(*
    PRG_Main
    Purpose : Cell entry point: the sorting cell unit (PackML, equipment, motion, part tracking).
    Task    : MainTask, cyclic 4 ms, SoftMotion bus cycle task
    Rule    : thin program - only instantiation and calls, no logic.
*)
PROGRAM PRG_Main
VAR
    sProjectVersion : STRING := GVL_Constants.PROJECT_VERSION;  // diagnostics: project version visible online and via OPC UA
END_VAR

// The sorting cell unit is instantiated here from Task 10 on.
