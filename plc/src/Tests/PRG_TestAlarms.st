(*
    PRG_TestAlarms
    Purpose : Simulation test harness for FB_AlarmHandler (tests/plc/alarms.json).
    Inputs  : eId + xRaise / xClear pulses, xAck, xReinit (each pulse resets itself).
*)
PROGRAM PRG_TestAlarms
VAR
    fbAlarms : FB_AlarmHandler;
    fbAlarmsInitial : FB_AlarmHandler;
    eId : E_AlarmId;
    xRaise : BOOL;
    xClear : BOOL;
    xAck : BOOL;
    xReinit : BOOL;
END_VAR

IF xReinit THEN
    xReinit := FALSE;
    fbAlarms := fbAlarmsInitial;
END_IF
IF xRaise THEN
    xRaise := FALSE;
    fbAlarms.Raise(eId);
END_IF
IF xClear THEN
    xClear := FALSE;
    fbAlarms.Clear(eId);
END_IF
IF xAck THEN
    xAck := FALSE;
    fbAlarms.AcknowledgeAll();
END_IF
fbAlarms();
