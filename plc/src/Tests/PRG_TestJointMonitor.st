(*
    PRG_TestJointMonitor
    Purpose : Simulation test harness for FB_JointMonitor (tests/plc/joint_monitor.json).
    Inputs  : xReinit; xAutoSeq - increment the feedback and setpoint sequences every cycle
              xRamp - J1 setpoint ramps by RAMP_STEP per cycle; iLag - feedback is the setpoint of
              iLag cycles earlier (and says so in udiFeedbackForSeq); xFreeze - feedback stands still
    Outputs : lrRampSpeed - measured J1 setpoint speed [deg/s]
*)
PROGRAM PRG_TestJointMonitor
VAR
    fbMon : FB_JointMonitor;
    fbAlarms : FB_AlarmHandler;
    fbMonInitial : FB_JointMonitor;
    fbAlarmsInitial : FB_AlarmHandler;
    xReinit : BOOL;
    xAutoSeq : BOOL;
    xRamp : BOOL;
    xFreeze : BOOL;
    iLag : INT;
    udiSpSeq : UDINT;
    aSpHist : ARRAY[0..127] OF LREAL;
    xRampOld : BOOL;
    tRampStart : TIME;
    lrRampStart : LREAL;
    lrRampSpeed : LREAL;
END_VAR
VAR CONSTANT
    RAMP_STEP : LREAL := 1.0;       // [deg per cycle]
END_VAR

IF xReinit THEN
    xReinit := FALSE;
    xAutoSeq := FALSE;
    xRamp := FALSE;
    xFreeze := FALSE;
    iLag := 0;
    udiSpSeq := 0;
    fbMon := fbMonInitial;
    fbAlarms := fbAlarmsInitial;
END_IF
IF xAutoSeq THEN
    fbMon.udiFeedbackSeq := fbMon.udiFeedbackSeq + 1;
    udiSpSeq := udiSpSeq + 1;
END_IF
IF xRamp THEN
    IF NOT xRampOld THEN
        tRampStart := TIME();
        lrRampStart := fbMon.aSetpoint[1];
    END_IF
    fbMon.aSetpoint[1] := fbMon.aSetpoint[1] + RAMP_STEP;
    IF TIME() > tRampStart THEN
        lrRampSpeed := (fbMon.aSetpoint[1] - lrRampStart) * 1000.0 / TIME_TO_LREAL(TIME() - tRampStart);
    END_IF
END_IF
xRampOld := xRamp;
aSpHist[udiSpSeq MOD 128] := fbMon.aSetpoint[1];
fbMon.udiSetpointSeq := udiSpSeq;
IF udiSpSeq >= INT_TO_UDINT(iLag) THEN
    fbMon.udiFeedbackForSeq := udiSpSeq - INT_TO_UDINT(iLag);
    IF NOT xFreeze THEN
        fbMon.aFeedback[1] := aSpHist[fbMon.udiFeedbackForSeq MOD 128];
    END_IF
END_IF
fbMon.itfAlarms := fbAlarms;
fbMon();
fbAlarms();
