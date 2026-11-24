(*
    FB_PickSequence
    Purpose : Pick-and-place cycle from the moving conveyor:
              home -> ready pose -> wait for a decided part in the pick window ->
              MC_TrackConveyorBelt (PCS_1 follows the part) -> linear approach / descend ->
              vacuum grip -> linear lift -> PTP to the target bin -> release -> retract.
    In/Out  : AxisGroup, ConveyorAxis, Robot (FB_Robot), Gripper (FB_VacuumGripper),
              Tracker (FB_PartTracker). The owner calls Robot, Gripper and Tracker each cycle.
    Inputs  : xRun - work on parts (FALSE: finish the current part, then go home and idle)
              xAbort - controlled stop now; the vacuum stays as it is (no dropped part)
              xReset - leave Error / Aborted to Idle. A part still held is placed in the
                       Quarantine bin on the next run; a scheduled part is marked missed.
    Outputs : eStep, xIdleAtHome, xBusy, udiPicked, udiPlaced, eLastBin, xPlacedPulse (one cycle)
    Errors  : every error first stops the robot (Aborting), then rests in Error.
    Window  : a pick is abandoned (part missed) if the part passes the pick window end before
              it is gripped.
    Moves   : linear only for the short tracked moves (PCS_1); PTP for long transfers, which
              avoids wrist/base singularities on Cartesian paths across the cell.
*)
FUNCTION_BLOCK FB_PickSequence
VAR_IN_OUT
    AxisGroup : AXIS_GROUP_REF_SM3;
    ConveyorAxis : AXIS_REF_SM3;
    Robot : FB_Robot;
    Gripper : FB_VacuumGripper;
    Tracker : FB_PartTracker;
END_VAR
VAR_INPUT
    xRun : BOOL;
    xAbort : BOOL;
    xReset : BOOL;
END_VAR
VAR_OUTPUT
    eStep : E_PickStep;
    xIdleAtHome : BOOL;
    xBusy : BOOL;
    udiPicked : UDINT;
    udiPlaced : UDINT;
    eLastBin : E_Bin;
    xPlacedPulse : BOOL;
END_VAR
VAR
    fbTrack : MC_TrackConveyorBelt;
    tonRelease : TON;
    xTrackExec : BOOL;
    uiIdx : UINT;                       // slot of the part being handled, 0 = none
    stPart : ST_PartRecord;
    stObject : MC_COORD_REF;
    stTarget : SMC_POS_REF;
    stHeld : ST_PartRecord;
    xAtHome : BOOL;
    xFaultPending : BOOL;               // Aborting was entered because of an error
    xRecover : BOOL;                    // a held part must go to quarantine on the next run
    // robot command handshake
    iCmdPhase : INT;
    xRequested : BOOL;
    eReqCmd : E_RobotCmd;
    stReqTarget : SMC_POS_REF;
    xCmdDone : BOOL;
    xCmdError : BOOL;
END_VAR
VAR CONSTANT
    RELEASE_TIME : TIME := T#200MS;      // vacuum off before retracting
END_VAR

xPlacedPulse := FALSE;
xCmdDone := FALSE;
xCmdError := FALSE;

// Robot command handshake: new command -> Execute FALSE -> TRUE -> wait for Done / Error.
CASE iCmdPhase OF
    1:
        Robot.eCmd := eReqCmd;
        Robot.stTarget := stReqTarget;
        Robot.xExecute := FALSE;
        iCmdPhase := 2;
    2:
        Robot.xExecute := TRUE;
        iCmdPhase := 3;
    3:
        IF Robot.xDone THEN
            Robot.xExecute := FALSE;
            iCmdPhase := 0;
            xCmdDone := TRUE;
        ELSIF Robot.xError THEN
            Robot.xExecute := FALSE;
            iCmdPhase := 0;
            xCmdError := TRUE;
        END_IF
END_CASE

fbTrack(AxisGroup := AxisGroup,
        ConveyorBelt := ConveyorAxis,
        Execute := xTrackExec,
        ConveyorBeltOrigin := GVL_CellGeometry.BELT_ORIGIN,
        InitialObjectPosition := stObject,
        CoordSystem := SMC_COORD_SYSTEM.PCS_1);

IF xAbort AND eStep <> E_PickStep.Idle AND eStep <> E_PickStep.Aborting
   AND eStep <> E_PickStep.Aborted AND eStep <> E_PickStep.Error THEN
    eStep := E_PickStep.Aborting;
    iCmdPhase := 0;
    xRequested := FALSE;
END_IF
IF xReset AND (eStep = E_PickStep.Error OR eStep = E_PickStep.Aborted) THEN
    IF Gripper.xHolding AND uiIdx > 0 THEN
        stPart.eTargetBin := E_Bin.Quarantine;       // unknown history: quarantine it
        xRecover := TRUE;
    ELSE
        Gripper.xCmdVacuum := FALSE;
        xRecover := FALSE;
        IF uiIdx > 0 THEN
            stHeld := Tracker.GetRecord(uiIdx);
            IF stHeld.eState = E_PartState.Scheduled OR stHeld.eState = E_PartState.Picked THEN
                Tracker.SetState(uiIdx, E_PartState.Missed);
            END_IF
            uiIdx := 0;
        END_IF
    END_IF
    eStep := E_PickStep.Idle;
    iCmdPhase := 0;
    xRequested := FALSE;
    xTrackExec := FALSE;
    xAtHome := FALSE;
    xFaultPending := FALSE;
    Robot.xExecute := FALSE;
END_IF

CASE eStep OF
    E_PickStep.Idle:
        IF xRun THEN
            IF xRecover THEN
                NextStep(E_PickStep.RecoverLift);   // a part is on the cup: straight up first
            ELSE
                NextStep(E_PickStep.MoveHome);
            END_IF
        END_IF

    E_PickStep.MoveHome:
        Request(E_RobotCmd.MovePtpAcs, GVL_CellGeometry.HOME_ACS);
        IF xCmdDone THEN
            xAtHome := TRUE;
            IF xRun THEN
                NextStep(E_PickStep.MoveReady);
            ELSE
                NextStep(E_PickStep.Idle);
            END_IF
        END_IF

    E_PickStep.RecoverLift:
        // after an abort the arm may stand anywhere (near the belt, a bin wall): lift vertically
        // to the ready height before any point-to-point move, whose path is not known
        stTarget := Robot.stActMcs;
        stTarget.c.Z := MAX(Robot.stActMcs.c.Z, GVL_CellGeometry.READY_POSE.Z);
        Request(E_RobotCmd.MoveLinMcs, stTarget);
        IF xCmdDone THEN
            NextStep(E_PickStep.MoveReady);
        END_IF

    E_PickStep.MoveReady:
        stTarget.c := GVL_CellGeometry.READY_POSE;
        Request(E_RobotCmd.MovePtpMcs, stTarget);
        IF xCmdDone THEN
            xAtHome := FALSE;
            IF xRecover THEN
                NextStep(E_PickStep.MoveToBin);     // the held part goes to its bin from Ready
            ELSE
                NextStep(E_PickStep.WaitPart);
            END_IF
        END_IF

    E_PickStep.WaitPart:
        IF NOT xRun THEN
            NextStep(E_PickStep.MoveHome);
        ELSE
            uiIdx := Tracker.NextPickable(GVL_CellGeometry.PE2_X,
                                          GVL_CellGeometry.PICK_WINDOW_END_X - GVL_CellGeometry.PICK_MARGIN);
            IF uiIdx > 0 THEN
                stPart := Tracker.GetRecord(uiIdx);
                stObject.X := Tracker.CurrentX(uiIdx);
                stObject.Y := stPart.lrY;
                stObject.Z := GVL_CellGeometry.BELT_SURFACE_Z;
                stObject.A := stPart.lrTheta;
                stObject.B := 0;
                stObject.C := 0;
                Tracker.SetState(uiIdx, E_PartState.Scheduled);
                xTrackExec := FALSE;
                NextStep(E_PickStep.StartTracking);
            END_IF
        END_IF

    E_PickStep.StartTracking:
        xTrackExec := TRUE;
        IF fbTrack.Done THEN
            NextStep(E_PickStep.Approach);
        ELSIF fbTrack.Error THEN
            GoError();
        END_IF

    E_PickStep.Approach:
        Request(E_RobotCmd.MoveLinPcs1, TrackedPose(GVL_CellGeometry.PART_HEIGHT + GVL_Params.lrApproachHeight));
        IF xCmdDone THEN
            NextStep(E_PickStep.Descend);
        END_IF

    E_PickStep.Descend:
        Request(E_RobotCmd.MoveLinPcs1, TrackedPose(GVL_CellGeometry.PART_HEIGHT - GVL_Params.lrPickDepth));
        IF xCmdDone THEN
            NextStep(E_PickStep.Grip);
        END_IF

    E_PickStep.Grip:
        Gripper.xCmdVacuum := TRUE;
        IF Gripper.xHolding THEN
            Tracker.SetState(uiIdx, E_PartState.Picked);
            udiPicked := udiPicked + 1;
            NextStep(E_PickStep.Lift);
        ELSIF Gripper.HasError THEN
            Gripper.xCmdVacuum := FALSE;          // nothing is held
            Tracker.SetState(uiIdx, E_PartState.Dropped);
            uiIdx := 0;
            GoError();
        END_IF

    E_PickStep.Lift:
        Request(E_RobotCmd.MoveLinPcs1, TrackedPose(GVL_CellGeometry.PART_HEIGHT + GVL_Params.lrApproachHeight));
        IF xCmdDone THEN
            xTrackExec := FALSE;
            NextStep(E_PickStep.MoveToBin);
        END_IF

    E_PickStep.MoveToBin:
        stTarget.c := GVL_CellGeometry.BIN_DROP[stPart.eTargetBin];
        Request(E_RobotCmd.MovePtpMcs, stTarget);
        IF xCmdDone THEN
            NextStep(E_PickStep.Release);
        END_IF

    E_PickStep.Release:
        Gripper.xCmdVacuum := FALSE;
        tonRelease(IN := TRUE, PT := RELEASE_TIME);
        IF tonRelease.Q THEN
            Tracker.SetState(uiIdx, E_PartState.Placed);
            uiIdx := 0;
            xRecover := FALSE;
            udiPlaced := udiPlaced + 1;
            eLastBin := stPart.eTargetBin;
            xPlacedPulse := TRUE;
            NextStep(E_PickStep.Retract);
        END_IF

    E_PickStep.Retract:
        stTarget.c := GVL_CellGeometry.BIN_DROP[stPart.eTargetBin];
        stTarget.c.Z := stTarget.c.Z + GVL_CellGeometry.RETRACT_HEIGHT;
        Request(E_RobotCmd.MoveLinMcs, stTarget);
        IF xCmdDone THEN
            IF xRun THEN
                NextStep(E_PickStep.MoveReady);
            ELSE
                NextStep(E_PickStep.MoveHome);
            END_IF
        END_IF

    E_PickStep.Aborting:
        Request(E_RobotCmd.Stop, stTarget);
        IF xCmdDone OR xCmdError THEN
            xTrackExec := FALSE;
            IF xFaultPending THEN
                xFaultPending := FALSE;
                NextStep(E_PickStep.Error);
            ELSE
                NextStep(E_PickStep.Aborted);
            END_IF
        END_IF

    E_PickStep.Aborted, E_PickStep.Error:
        ;   // wait for xReset
END_CASE

// The part passed the pick window end before it was gripped: give it up, do not chase it.
IF (eStep = E_PickStep.StartTracking OR eStep = E_PickStep.Approach OR eStep = E_PickStep.Descend
    OR eStep = E_PickStep.Grip) AND uiIdx > 0 AND NOT Gripper.xHolding
   AND Tracker.CurrentX(uiIdx) > GVL_CellGeometry.PICK_WINDOW_END_X THEN
    Gripper.xCmdVacuum := FALSE;
    Tracker.SetState(uiIdx, E_PartState.Missed);
    uiIdx := 0;
    xTrackExec := FALSE;
    iCmdPhase := 0;
    Robot.xExecute := FALSE;
    NextStep(E_PickStep.MoveReady);
END_IF

// A part lost while carrying it: stop the robot; the valve stays on (spec 5.4: no release outside
// a bin), Stopping / recovery decide what happens next.
IF (eStep = E_PickStep.Lift OR eStep = E_PickStep.MoveToBin) AND Gripper.HasError THEN
    Tracker.SetState(uiIdx, E_PartState.Dropped);
    uiIdx := 0;
    GoError();
END_IF
IF xCmdError AND eStep <> E_PickStep.Aborting AND eStep <> E_PickStep.Aborted
   AND eStep <> E_PickStep.Error THEN
    GoError();
END_IF

xIdleAtHome := eStep = E_PickStep.Idle AND xAtHome;
xBusy := eStep <> E_PickStep.Idle AND eStep <> E_PickStep.WaitPart
         AND eStep <> E_PickStep.Aborted AND eStep <> E_PickStep.Error;
