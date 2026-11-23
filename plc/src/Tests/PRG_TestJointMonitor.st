(*
    PRG_TestJointMonitor
    Purpose : Simulation test harness for FB_JointMonitor (tests/plc/joint_monitor.json).
    Inputs  : xReinit; xAutoSeq - increment the feedback sequence every cycle (fresh feedback)
*)
PROGRAM PRG_TestJointMonitor
VAR
    fbMon : FB_JointMonitor;
    fbAlarms : FB_AlarmHandler;
    fbMonInitial : FB_JointMonitor;
    fbAlarmsInitial : FB_AlarmHandler;
    xReinit : BOOL;
    xAutoSeq : BOOL;
END_VAR

IF xReinit THEN
    xReinit := FALSE;
    xAutoSeq := FALSE;
    fbMon := fbMonInitial;
    fbAlarms := fbAlarmsInitial;
END_IF
IF xAutoSeq THEN
    fbMon.udiFeedbackSeq := fbMon.udiFeedbackSeq + 1;
END_IF
fbMon.itfAlarms := fbAlarms;
fbMon();
fbAlarms();
