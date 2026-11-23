(*
    FB_SortingCell
    Purpose : The sorting cell as one PackML unit. Owns all equipment and maps the PackML states
              to equipment actions; computes the interlocks.
    In/Out  : AxisGroup (AxisGroup_Robot), ConveyorAxis (Axis_Conveyor)
    Inputs  : operator commands (GVL_Hmi), sensors and messages (GVL_Bridge), xLoopback
    Outputs : setpoints, belt and vacuum to the bridge; eState, eMode, ePickStep, aActAcs
    States  : Resetting  - acknowledge alarms, reset equipment; done when safe and fault-free
              Starting / Unholding / Unsuspending - robot home -> ready, conveyor at speed
              Execute    - automatic: pick sequence runs; Manual: jogging
              Stopping / Holding / Suspending / Completing - finish the current part, go home
              Aborting   - controlled stop, vacuum kept; Clearing - reset the sequence
    Interlocks: Critical alarm or not safe -> Abort; Error alarm -> Stop; any bin full -> Suspend
*)
FUNCTION_BLOCK FB_SortingCell
VAR_IN_OUT
    AxisGroup : AXIS_GROUP_REF_SM3;
    ConveyorAxis : AXIS_REF_SM3;
END_VAR
VAR_INPUT
    eCommand : E_PackMLCommand;
    eModeRequest : E_PackMLMode := E_PackMLMode.Production;
    xAlarmAck : BOOL;
    axJogPlus : ARRAY[1..6] OF BOOL;
    axJogMinus : ARRAY[1..6] OF BOOL;
    rOverride : REAL := 1.0;
    xHeartbeat : BOOL;
    aJointPosFb : ARRAY[1..6] OF LREAL;
    aJointTorqueFb : ARRAY[1..6] OF LREAL;
    udiFeedbackSeq : UDINT;
    xPE1 : BOOL;
    xVacuumOk : BOOL;
    axBinFull : ARRAY[E_Bin.TypeA..E_Bin.Quarantine] OF BOOL;
    xDoorClosed : BOOL := TRUE;
    xEStopOk : BOOL := TRUE;
    stVision : ST_VisionMsg;
    stDecision : ST_DecisionMsg;
    xLoopback : BOOL;
END_VAR
VAR_OUTPUT
    aJointPosSp : ARRAY[1..6] OF LREAL;
    lrBeltPos : LREAL;
    lrBeltVel : LREAL;
    xVacuumOn : BOOL;
    stCapture : ST_CaptureMsg;
    eState : E_PackMLState := E_PackMLState.Stopped;
    eMode : E_PackMLMode := E_PackMLMode.Production;
    ePickStep : E_PickStep;
    aActAcs : ARRAY[1..6] OF LREAL;
END_VAR
VAR
    fbSm : FB_PackMLStateMachine;
    fbAlarms : FB_AlarmHandler;
    fbSafety : FB_SafetyMonitor;
    fbConv : FB_Conveyor;
    fbRobot : FB_Robot;
    fbMon : FB_JointMonitor;
    fbTracker : FB_PartTracker;
    fbSeq : FB_PickSequence;
    fbVac : FB_VacuumGripper;
    aBins : ARRAY[E_Bin.TypeA..E_Bin.Quarantine] OF FB_Bin;
    fbPe1 : FB_PhotoEye;
    fbWatchdog : FB_BridgeWatchdog;
    fbJog : SMC_GroupJog2;
    eBin : E_Bin;
    i : INT;
    xAnyBinFull : BOOL;
    xComplete : BOOL;
    xAutoMode : BOOL;
    xRunBelt : BOOL;
    xJog : BOOL;
    lrSpeedFactor : LREAL;
    aFeedback : ARRAY[1..6] OF LREAL;
END_VAR
VAR CONSTANT
    REDUCED_SPEED_FACTOR : LREAL := 0.25;   // Maintenance mode and Manual with the door open
    JOG_VELOCITY : LREAL := 30;             // [deg/s] joint jog
    JOG_ACCELERATION : LREAL := 300;        // [deg/s2]
    JOG_JERK : LREAL := 3000;               // [deg/s3]
    JOG_MAX_LINEAR : LREAL := 100;          // [mm] per jog edge
    JOG_MAX_ANGULAR : LREAL := 45;          // [deg] per jog edge
END_VAR

eState := fbSm.eState;
eMode := fbSm.eMode;
xAutoMode := eMode <> E_PackMLMode.Manual;

fbRobot.itfAlarms := fbAlarms;
fbConv.itfAlarms := fbAlarms;
fbVac.itfAlarms := fbAlarms;
fbTracker.itfAlarms := fbAlarms;
fbSafety.itfAlarms := fbAlarms;
fbMon.itfAlarms := fbAlarms;
fbWatchdog.itfAlarms := fbAlarms;

// --- safety and alarm acknowledgement --------------------------------------------------------
fbSafety(xEStopOk := xEStopOk, xDoorClosed := xDoorClosed, eMode := eMode,
         xResetCmd := eState = E_PackMLState.Resetting OR eState = E_PackMLState.Clearing);
IF xAlarmAck OR (fbSm.xStateChanged AND (eState = E_PackMLState.Resetting OR eState = E_PackMLState.Clearing)) THEN
    fbAlarms.AcknowledgeAll();
END_IF

// --- bins --------------------------------------------------------------------------------------
xAnyBinFull := FALSE;
FOR eBin := E_Bin.TypeA TO E_Bin.Quarantine DO
    aBins[eBin](eBin := eBin,
                xFullSensor := axBinFull[eBin],
                xPlaced := fbSeq.xPlacedPulse AND fbSeq.eLastBin = eBin);
    xAnyBinFull := xAnyBinFull OR aBins[eBin].xFull;
END_FOR
IF xAnyBinFull THEN
    fbAlarms.Raise(E_AlarmId.BinFull);
ELSE
    fbAlarms.Clear(E_AlarmId.BinFull);
END_IF

// --- PackML state actions ----------------------------------------------------------------------
xComplete := FALSE;
xRunBelt := FALSE;
xJog := FALSE;
fbSeq.xRun := FALSE;
fbSeq.xAbort := FALSE;
fbSeq.xReset := FALSE;
CASE eState OF
    E_PackMLState.Resetting:
        fbRobot.Reset();
        fbVac.Reset();
        fbConv.Reset();
        xComplete := fbSafety.xSafeToMove AND fbRobot.xReady
                     AND NOT fbAlarms.xCriticalActive AND NOT fbAlarms.xErrorActive;

    E_PackMLState.Starting, E_PackMLState.Unholding, E_PackMLState.Unsuspending:
        IF xAutoMode THEN
            fbSeq.xRun := TRUE;
            xRunBelt := TRUE;
            xComplete := fbSeq.eStep = E_PickStep.WaitPart AND fbConv.xAtSpeed;
        ELSE
            xComplete := fbRobot.xReady;
        END_IF

    E_PackMLState.Execute:
        IF xAutoMode THEN
            fbSeq.xRun := TRUE;
            xRunBelt := TRUE;
        ELSE
            xJog := TRUE;
        END_IF

    E_PackMLState.Stopping, E_PackMLState.Holding, E_PackMLState.Suspending, E_PackMLState.Completing:
        xComplete := fbSeq.eStep = E_PickStep.Idle OR fbSeq.eStep = E_PickStep.Error
                     OR fbSeq.eStep = E_PickStep.Aborted;

    E_PackMLState.Aborting:
        fbSeq.xAbort := TRUE;
        xComplete := NOT fbRobot.xMoving AND (fbSeq.eStep = E_PickStep.Aborted
                     OR fbSeq.eStep = E_PickStep.Idle OR fbSeq.eStep = E_PickStep.Error);

    E_PackMLState.Clearing:
        fbSeq.xReset := TRUE;
        fbRobot.Reset();
        fbVac.Reset();
        fbConv.Reset();
        xComplete := fbSafety.xSafeToMove AND fbSeq.eStep = E_PickStep.Idle
                     AND NOT fbAlarms.xCriticalActive;
END_CASE

// --- equipment ---------------------------------------------------------------------------------
IF eMode = E_PackMLMode.Maintenance OR fbSafety.xReducedSpeed THEN
    lrSpeedFactor := REDUCED_SPEED_FACTOR;
ELSE
    lrSpeedFactor := 1.0;
END_IF

fbPe1(xRaw := xPE1);
fbTracker(lrBeltPos := fbConv.lrPosition, xPE1Rising := fbPe1.xRising,
          stVision := stVision, stDecision := stDecision);
fbSeq(AxisGroup := AxisGroup, ConveyorAxis := ConveyorAxis,
      Robot := fbRobot, Gripper := fbVac, Tracker := fbTracker);
fbVac(xVacuumOk := xVacuumOk);

fbRobot.xEnable := eState <> E_PackMLState.Stopped;
fbRobot.lrOverride := REAL_TO_LREAL(rOverride) * lrSpeedFactor;
fbRobot(AxisGroup := AxisGroup);

fbJog.Enable := xJog AND fbRobot.xReady AND fbSafety.xSafeToMove;
FOR i := 1 TO 6 DO
    fbJog.Forward[i - 1] := axJogPlus[i];
    fbJog.Backward[i - 1] := axJogMinus[i];
END_FOR
fbJog(AxisGroup := AxisGroup,
      CoordSystem := SMC_COORD_SYSTEM.ACS,
      MaxLinearDistance := JOG_MAX_LINEAR,
      MaxAngularDistance := JOG_MAX_ANGULAR,
      Velocity := JOG_VELOCITY,
      Acceleration := JOG_ACCELERATION,
      Deceleration := JOG_ACCELERATION,
      Jerk := JOG_JERK,
      VelFactor := lrSpeedFactor,
      AccFactor := 1.0,
      JerkFactor := 1.0);

fbConv(Axis := ConveyorAxis,
       xEnable := eState <> E_PackMLState.Stopped,
       lrVelocity := GVL_Params.lrBeltSpeed,
       xRun := xRunBelt AND fbSafety.xSafeToMove);

FOR i := 1 TO 6 DO
    IF xLoopback THEN
        aFeedback[i] := fbRobot.aSetAcs[i];
    ELSE
        aFeedback[i] := aJointPosFb[i];
    END_IF
END_FOR
fbMon(aSetpoint := fbRobot.aSetAcs, aFeedback := aFeedback, aTorque := aJointTorqueFb,
      udiFeedbackSeq := udiFeedbackSeq, xLoopback := xLoopback, xActive := fbRobot.xReady);
fbWatchdog(xHeartbeat := xHeartbeat, xEnable := NOT xLoopback AND eState <> E_PackMLState.Stopped);

// --- PackML ------------------------------------------------------------------------------------
fbAlarms();
fbSm(eCommand := eCommand,
     eModeRequest := eModeRequest,
     xStateComplete := xComplete,
     xAbortRequest := fbAlarms.xCriticalActive OR NOT fbSafety.xSafeToMove,
     xStopRequest := fbAlarms.xErrorActive,
     xSuspendRequest := xAnyBinFull,
     xUnsuspendRequest := NOT xAnyBinFull);

// --- outputs to the bridge ---------------------------------------------------------------------
aJointPosSp := fbRobot.aSetAcs;
lrBeltPos := fbConv.lrPosition;
lrBeltVel := fbConv.lrActVelocity;
xVacuumOn := fbVac.xValveOn;
stCapture := fbTracker.stCapture;
eState := fbSm.eState;
eMode := fbSm.eMode;
ePickStep := fbSeq.eStep;
FOR i := 1 TO 6 DO
    CASE i OF
        1: aActAcs[i] := fbRobot.stActAcs.a.a0;
        2: aActAcs[i] := fbRobot.stActAcs.a.a1;
        3: aActAcs[i] := fbRobot.stActAcs.a.a2;
        4: aActAcs[i] := fbRobot.stActAcs.a.a3;
        5: aActAcs[i] := fbRobot.stActAcs.a.a4;
        6: aActAcs[i] := fbRobot.stActAcs.a.a5;
    END_CASE
END_FOR
