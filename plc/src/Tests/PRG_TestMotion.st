(*
    PRG_TestMotion
    Purpose : Simulation test harness for FB_Robot and FB_Conveyor (tests/plc/motion.json).
    Inputs  : xActive - only then are the FBs called; xGo - start eCmd with the target chosen by
              iTargetSel (1 = home, 2 = current TCP - 50 mm in Z, 3 = home with J1 = 60 deg,
              4 = stProbe as written by the test)
    Outputs : xLastDone / xLastError of the last command, udiMoveMsLast / udiMoveMsPrev,
              xSlower (last move took > 1.5 x the previous one), lrZDelta
    Note    : SoftMotion FB instances are never re-initialised by assignment (corrupts them).
*)
PROGRAM PRG_TestMotion
VAR
    fbRobot : FB_Robot;
    fbConv : FB_Conveyor;
    fbAlarms : FB_AlarmHandler;
    xActive : BOOL;
    iTargetSel : INT;
    eCmd : E_RobotCmd;
    xGo : BOOL;
    iGoStep : INT;
    xLastDone : BOOL;
    xLastError : BOOL;
    tStart : TIME;
    udiMoveMsLast : UDINT;
    udiMoveMsPrev : UDINT;
    xSlower : BOOL;
    lrZStart : LREAL;
    lrZDelta : LREAL;
    stTarget : SMC_POS_REF;
    stProbe : SMC_POS_REF;
END_VAR

IF NOT xActive THEN
    RETURN;
END_IF
fbRobot.itfAlarms := fbAlarms;
fbConv.itfAlarms := fbAlarms;

IF xGo THEN
    xGo := FALSE;
    CASE iTargetSel OF
        1: stTarget := GVL_CellGeometry.HOME_ACS;
        2: stTarget := fbRobot.stActMcs;
           lrZStart := fbRobot.stActMcs.c.Z;
           stTarget.c.Z := lrZStart - 50;
        3: stTarget := GVL_CellGeometry.HOME_ACS;
           stTarget.a.a0 := 60;
        4: stTarget := stProbe;
    END_CASE
    fbRobot.stTarget := stTarget;
    fbRobot.eCmd := eCmd;
    fbRobot.xExecute := FALSE;     // a fresh rising edge, even if a command is running
    iGoStep := 1;
    xLastDone := FALSE;
    xLastError := FALSE;
ELSIF iGoStep = 1 THEN
    fbRobot.xExecute := TRUE;
    tStart := TIME();
    iGoStep := 2;
ELSIF iGoStep = 2 AND (fbRobot.xDone OR fbRobot.xError) THEN
    xLastDone := fbRobot.xDone;
    xLastError := fbRobot.xError;
    udiMoveMsPrev := udiMoveMsLast;
    udiMoveMsLast := TIME_TO_UDINT(TIME() - tStart);
    xSlower := udiMoveMsLast * 2 > udiMoveMsPrev * 3;
    fbRobot.xExecute := FALSE;
    iGoStep := 0;
END_IF

fbRobot(AxisGroup := AxisGroup_Robot);
fbConv(Axis := Axis_Conveyor);
fbAlarms();
IF iTargetSel = 2 THEN
    lrZDelta := fbRobot.stActMcs.c.Z - lrZStart;
END_IF
