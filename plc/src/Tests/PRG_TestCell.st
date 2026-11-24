(*
    PRG_TestCell
    Purpose : Simulation test harness for the whole cell in PRG_Main (tests/plc/cell.json).
              Simulates the vacuum switch, injects parts (PE1 pulse, then vision and decision
              messages for the captured part id) and can press the E-stop or lose the vacuum
              during a transfer. Can play the twin's bridge (heartbeat, joint feedback answering
              the current setpoint sample, twin active) and stall it.
    Inputs  : xActive; xInject (+ usiInjClass, eInjQuality); xEStopOnTransfer; xVacLostOnTransfer;
              xMark (J1 reference); xBridgeSim; xBridgeStall (heartbeat stops toggling);
              xBridgeStallOnTransfer
    Outputs : lrJ1Delta - J1 movement since xMark [deg]; lrAbortDelayMs - bridge stall -> Aborted
*)
PROGRAM PRG_TestCell
VAR
    xActive : BOOL;
    xInject : BOOL;
    usiInjClass : USINT;
    eInjQuality : E_Quality := E_Quality.Ok;
    iInject : INT;
    tonPulse : TON;
    tonVac : TON;
    xEStopOnTransfer : BOOL;
    xVacLostOnTransfer : BOOL;
    xVacLost : BOOL;                    // latched until xVacLostOnTransfer is released
    xMark : BOOL;
    lrJ1Start : LREAL;
    lrJ1Delta : LREAL;
    xBridgeSim : BOOL;
    xBridgeStall : BOOL;
    xBridgeStallOnTransfer : BOOL;      // stall the bridge when the robot carries a part to its bin
    xStallTimed : BOOL;
    tStall : TIME;
    lrAbortDelayMs : LREAL;             // stall -> Aborted [ms]
END_VAR
VAR CONSTANT
    PE1_PULSE : TIME := T#250MS;
END_VAR

IF NOT xActive THEN
    RETURN;
END_IF

IF xVacLostOnTransfer AND PRG_Main.fbCell.ePickStep = E_PickStep.MoveToBin THEN
    xVacLost := TRUE;
ELSIF NOT xVacLostOnTransfer THEN
    xVacLost := FALSE;
END_IF
tonVac(IN := GVL_Bridge.xVacuumOn, PT := T#100MS);
GVL_Bridge.xVacuumOk := tonVac.Q AND NOT xVacLost;

// the twin's bridge: feedback answers the current setpoint sample, heartbeat toggles
IF xBridgeStallOnTransfer AND NOT xBridgeStall AND PRG_Main.fbCell.ePickStep = E_PickStep.MoveToBin THEN
    xBridgeStall := TRUE;
    xStallTimed := FALSE;
    tStall := TIME();
END_IF
IF xBridgeStall AND NOT xStallTimed AND GVL_Bridge.eState = E_PackMLState.Aborted THEN
    xStallTimed := TRUE;
    lrAbortDelayMs := TIME_TO_LREAL(TIME() - tStall);
END_IF
IF xBridgeSim THEN
    GVL_Bridge.xTwinActive := TRUE;
    GVL_Bridge.aJointPosFb := GVL_Bridge.aJointPosSp;
    GVL_Bridge.udiFeedbackForSeq := GVL_Bridge.udiSetpointSeq;
    IF NOT xBridgeStall THEN
        GVL_Bridge.xHeartbeat := NOT GVL_Bridge.xHeartbeat;
        GVL_Bridge.udiFeedbackSeq := GVL_Bridge.udiFeedbackSeq + 1;
    END_IF
END_IF

CASE iInject OF
    0:
        IF xInject THEN
            xInject := FALSE;
            GVL_Bridge.xPE1 := TRUE;
            iInject := 1;
        END_IF
    1:
        tonPulse(IN := TRUE, PT := PE1_PULSE);
        IF tonPulse.Q THEN
            tonPulse(IN := FALSE);
            GVL_Bridge.xPE1 := FALSE;
            iInject := 2;
        END_IF
    2:
        GVL_Bridge.stVision.udiPartId := GVL_Bridge.stCapture.udiPartId;
        GVL_Bridge.stVision.xValid := TRUE;
        GVL_Bridge.stVision.usiClass := usiInjClass;
        GVL_Bridge.stVision.rConfidence := 0.9;
        GVL_Bridge.stVision.lrX := GVL_CellGeometry.PE1_X;
        GVL_Bridge.stVision.lrY := 0;
        GVL_Bridge.stVision.lrTheta := 0;
        GVL_Bridge.stVision.udiSeq := GVL_Bridge.stVision.udiSeq + 1;
        iInject := 3;
    3:
        GVL_Bridge.stDecision.udiPartId := GVL_Bridge.stVision.udiPartId;
        GVL_Bridge.stDecision.eQuality := eInjQuality;
        GVL_Bridge.stDecision.rQualityProb := 0.95;
        GVL_Bridge.stDecision.xIdentReliable := TRUE;
        GVL_Bridge.stDecision.udiSeq := GVL_Bridge.stDecision.udiSeq + 1;
        iInject := 0;
END_CASE

IF xEStopOnTransfer AND PRG_Main.fbCell.ePickStep = E_PickStep.MoveToBin THEN
    GVL_Bridge.xEStopOk := FALSE;
END_IF

IF xMark THEN
    xMark := FALSE;
    lrJ1Start := PRG_Main.fbCell.aActAcs[1];
END_IF
lrJ1Delta := PRG_Main.fbCell.aActAcs[1] - lrJ1Start;
