(*
    PRG_TestPackML
    Purpose : Simulation test harness for FB_PackMLStateMachine (tests/plc/packml.json).
    Inputs  : xReinit - TRUE re-initialises the state machine, then resets itself.
*)
PROGRAM PRG_TestPackML
VAR
    fbSm : FB_PackMLStateMachine;
    fbSmInitial : FB_PackMLStateMachine;
    xReinit : BOOL;
END_VAR

IF xReinit THEN
    xReinit := FALSE;
    fbSm := fbSmInitial;
END_IF
fbSm();
