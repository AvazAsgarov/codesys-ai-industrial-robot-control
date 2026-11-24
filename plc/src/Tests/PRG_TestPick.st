(*
    PRG_TestPick
    Purpose : Simulation test harness for FB_PickSequence (tests/plc/pick.json). Owns the robot,
              conveyor, gripper, tracker and alarms like the cell does, and simulates the vacuum
              switch (OK 100 ms after the valve opens).
    Inputs  : xActive, xBeltRun, xInject (+ usiInjClass, eInjQuality, lrInjX: one part with
              vision and decision; xInjInvalid: the vision message says "not seen"),
              xDropOnTransfer (vacuum lost during MoveToBin),
              xAbortOnLift (abort when the sequence reaches Lift), xResetSeq
    Outputs : xSawRecoverLift (latched: the recovery after an abort lifted first),
              lrGripZ (TCP height when the last grip started) [mm]
    Note    : SoftMotion FB instances are never re-initialised by assignment.
*)
PROGRAM PRG_TestPick
VAR
    fbRobot : FB_Robot;
    fbConv : FB_Conveyor;
    fbVac : FB_VacuumGripper;
    fbTracker : FB_PartTracker;
    fbAlarms : FB_AlarmHandler;
    fbSeq : FB_PickSequence;
    xActive : BOOL;
    xBeltRun : BOOL;
    xInject : BOOL;
    xInjInvalid : BOOL;
    usiInjClass : USINT;
    eInjQuality : E_Quality := E_Quality.Ok;
    lrInjX : LREAL := 1000;
    iInject : INT;
    xPE1 : BOOL;
    stVis : ST_VisionMsg;
    stDec : ST_DecisionMsg;
    xDropOnTransfer : BOOL;
    xAbortOnLift : BOOL;
    xResetSeq : BOOL;
    xVacLost : BOOL;
    tonVac : TON;
    xSawRecoverLift : BOOL;
    lrGripZ : LREAL;
    eLastStep : E_PickStep;
END_VAR

IF NOT xActive THEN
    RETURN;
END_IF
fbRobot.itfAlarms := fbAlarms;
fbConv.itfAlarms := fbAlarms;
fbVac.itfAlarms := fbAlarms;
fbTracker.itfAlarms := fbAlarms;
fbConv.xEnable := TRUE;
fbConv.lrVelocity := GVL_Params.lrBeltSpeed;
fbConv.xRun := xBeltRun;
fbRobot.xEnable := TRUE;

// One injected part: capture, then vision, then decision on consecutive cycles.
CASE iInject OF
    0:
        IF xInject THEN
            xInject := FALSE;
            xPE1 := TRUE;
            iInject := 1;
        END_IF
    1:
        xPE1 := FALSE;
        iInject := 2;
    2:
        stVis.udiSeq := stVis.udiSeq + 1;
        stVis.udiPartId := fbTracker.stCapture.udiPartId;
        stVis.xValid := NOT xInjInvalid;
        stVis.usiClass := usiInjClass;
        stVis.rConfidence := 0.9;
        stVis.lrX := lrInjX;
        stVis.lrY := 0;
        stVis.lrTheta := 0;
        iInject := 3;
    3:
        stDec.udiSeq := stDec.udiSeq + 1;
        stDec.udiPartId := stVis.udiPartId;
        stDec.eQuality := eInjQuality;
        stDec.rQualityProb := 0.95;
        stDec.xIdentReliable := TRUE;
        iInject := 0;
END_CASE

IF xDropOnTransfer AND fbSeq.eStep = E_PickStep.MoveToBin THEN
    xVacLost := TRUE;
END_IF
tonVac(IN := fbVac.xValveOn AND NOT xVacLost, PT := T#100MS);
fbVac.xVacuumOk := tonVac.Q;
IF xAbortOnLift AND fbSeq.eStep = E_PickStep.Lift THEN
    fbSeq.xAbort := TRUE;
END_IF
fbSeq.xReset := xResetSeq;
IF xResetSeq THEN
    xResetSeq := FALSE;
    xVacLost := FALSE;
    fbSeq.xAbort := FALSE;
    fbVac.Reset();
    fbAlarms.AcknowledgeAll();
END_IF

fbTracker(lrBeltPos := fbConv.lrPosition, xPE1Rising := xPE1, stVision := stVis, stDecision := stDec);
fbSeq(AxisGroup := AxisGroup_Robot, ConveyorAxis := Axis_Conveyor, Robot := fbRobot, Gripper := fbVac, Tracker := fbTracker);
fbVac();
fbRobot(AxisGroup := AxisGroup_Robot);
fbConv(Axis := Axis_Conveyor);
fbAlarms();
IF fbSeq.eStep = E_PickStep.RecoverLift THEN
    xSawRecoverLift := TRUE;
END_IF
IF fbSeq.eStep = E_PickStep.Grip AND eLastStep <> E_PickStep.Grip THEN
    lrGripZ := fbRobot.stActMcs.c.Z;
END_IF
eLastStep := fbSeq.eStep;
