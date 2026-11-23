(*
    FB_Robot
    Purpose : The 6-axis robot (SoftMotion axis group) behind a PLCopen-style command interface.
    In/Out  : AxisGroup - AxisGroup_Robot
    Inputs  : xEnable - power and enable the group
              eCmd + stTarget - command, started by a rising edge of xExecute
              lrOverride - speed override ]0, 1] for all movements
    Outputs : xReady (enabled, no error), xBusy / xDone / xError of the running command,
              eSmcError, xMoving, stActAcs, stActMcs, aSetAcs[1..6] (joint setpoints, deg)
    Alarms  : AxisGroupError
    Note    : call once per cycle in the SoftMotion bus cycle task.
*)
FUNCTION_BLOCK FB_Robot IMPLEMENTS I_Equipment
VAR_IN_OUT
    AxisGroup : AXIS_GROUP_REF_SM3;
END_VAR
VAR_INPUT
    xEnable : BOOL;
    eCmd : E_RobotCmd;
    stTarget : SMC_POS_REF;
    xExecute : BOOL;
    lrOverride : LREAL := 1.0;
    itfAlarms : I_AlarmSink;
END_VAR
VAR_OUTPUT
    xReady : BOOL;
    xBusy : BOOL;
    xDone : BOOL;
    xError : BOOL;
    eSmcError : SMC_ERROR;
    xMoving : BOOL;
    stActAcs : SMC_POS_REF;
    stActMcs : SMC_POS_REF;
    aSetAcs : ARRAY[1..6] OF LREAL;
END_VAR
VAR CONSTANT
    MIN_OVERRIDE : LREAL := 0.01;
    STOP_DECELERATION : LREAL := 5000;     // path deceleration of a controlled stop [mm/s2]
    STOP_JERK : LREAL := 100000;           // path jerk of a controlled stop [mm/s3]
END_VAR
VAR
    fbPower : SMC_GroupPower;
    fbEnable : MC_GroupEnable;
    fbReset : MC_GroupReset;
    fbStop : MC_GroupStop := (Deceleration := STOP_DECELERATION, Jerk := STOP_JERK);
    fbOverride : MC_GroupSetOverride;
    fbPtp : MC_MoveDirectAbsolute := (CoordSystem := SMC_COORD_SYSTEM.ACS);
    fbLin : MC_MoveLinearAbsolute;
    fbReadAcs : MC_GroupReadActualPosition := (Enable := TRUE, CoordSystem := SMC_COORD_SYSTEM.ACS);
    fbReadMcs : MC_GroupReadActualPosition := (Enable := TRUE, CoordSystem := SMC_COORD_SYSTEM.MCS);
    fbReadSet : SMC_GroupReadSetPosition := (Enable := TRUE, CoordSystem := SMC_COORD_SYSTEM.ACS);
    fbStatus : MC_GroupReadStatus := (Enable := TRUE);
    rtExecute : R_TRIG;
    eActive : E_RobotCmd;
    xResetRequest : BOOL;
    xFault : BOOL;
    lrOverrideLimited : LREAL;
END_VAR

rtExecute(CLK := xExecute);
IF rtExecute.Q THEN
    eActive := eCmd;
ELSIF NOT xExecute THEN
    eActive := E_RobotCmd.None;
END_IF
IF eActive = E_RobotCmd.Reset THEN
    xResetRequest := TRUE;
END_IF

fbStatus(AxisGroup := AxisGroup);
fbPower(AxisGroup := AxisGroup, Enable := xEnable, bRegulatorOn := xEnable, bDriveStart := xEnable);
fbEnable(AxisGroup := AxisGroup, Execute := fbPower.Status AND NOT xResetRequest);

lrOverrideLimited := LIMIT(MIN_OVERRIDE, lrOverride, 1.0);
fbOverride(AxisGroup := AxisGroup,
           Enable := fbEnable.Done AND NOT fbStatus.GroupStopping AND NOT fbStatus.GroupErrorStop,
           VelFactor := lrOverrideLimited,
           PathVelFactor := lrOverrideLimited);

fbPtp.Position := stTarget;
fbPtp.VelFactor := GVL_Params.lrPtpVelFactor;
IF eActive = E_RobotCmd.MovePtpMcs THEN
    fbPtp.CoordSystem := SMC_COORD_SYSTEM.MCS;
ELSE
    fbPtp.CoordSystem := SMC_COORD_SYSTEM.ACS;
END_IF
fbPtp(AxisGroup := AxisGroup, Execute := eActive = E_RobotCmd.MovePtpAcs OR eActive = E_RobotCmd.MovePtpMcs);

fbLin.Position := stTarget;
fbLin.Velocity := GVL_Params.lrLinVelocity;
fbLin.Acceleration := GVL_Params.lrLinAccel;
fbLin.Deceleration := GVL_Params.lrLinAccel;
fbLin.Jerk := GVL_Params.lrLinJerk;
IF eActive = E_RobotCmd.MoveLinPcs1 THEN
    fbLin.CoordSystem := SMC_COORD_SYSTEM.PCS_1;
ELSE
    fbLin.CoordSystem := SMC_COORD_SYSTEM.MCS;
END_IF
fbLin(AxisGroup := AxisGroup, Execute := eActive = E_RobotCmd.MoveLinMcs OR eActive = E_RobotCmd.MoveLinPcs1);

fbStop(AxisGroup := AxisGroup, Execute := eActive = E_RobotCmd.Stop);
fbReset(AxisGroup := AxisGroup, Execute := xResetRequest);
IF xResetRequest AND (fbReset.Done OR fbReset.Error) THEN
    xResetRequest := FALSE;
    IF fbReset.Done THEN
        IF xFault AND itfAlarms <> 0 THEN
            itfAlarms.Clear(E_AlarmId.AxisGroupError);
        END_IF
        xFault := FALSE;
        eSmcError := SMC_ERROR.SMC_NO_ERROR;
    END_IF
END_IF

fbReadAcs(AxisGroup := AxisGroup);
fbReadMcs(AxisGroup := AxisGroup);
fbReadSet(AxisGroup := AxisGroup);
stActAcs := fbReadAcs.Position;
stActMcs := fbReadMcs.Position;
aSetAcs[1] := fbReadSet.Position.a.a0;
aSetAcs[2] := fbReadSet.Position.a.a1;
aSetAcs[3] := fbReadSet.Position.a.a2;
aSetAcs[4] := fbReadSet.Position.a.a3;
aSetAcs[5] := fbReadSet.Position.a.a4;
aSetAcs[6] := fbReadSet.Position.a.a5;

CASE eActive OF
    E_RobotCmd.MovePtpAcs, E_RobotCmd.MovePtpMcs:
        xBusy := fbPtp.Busy; xDone := fbPtp.Done; xError := fbPtp.Error;
        IF fbPtp.Error THEN eSmcError := fbPtp.ErrorID; END_IF
    E_RobotCmd.MoveLinMcs, E_RobotCmd.MoveLinPcs1:
        xBusy := fbLin.Busy; xDone := fbLin.Done; xError := fbLin.Error;
        IF fbLin.Error THEN eSmcError := fbLin.ErrorID; END_IF
    E_RobotCmd.Stop:
        xBusy := fbStop.Busy; xDone := fbStop.Done; xError := fbStop.Error;
        IF fbStop.Error THEN eSmcError := fbStop.ErrorID; END_IF
    E_RobotCmd.Reset:
        xBusy := xResetRequest; xDone := NOT xResetRequest AND NOT xFault; xError := fbReset.Error;
ELSE
    xBusy := FALSE; xDone := FALSE; xError := FALSE;
END_CASE

IF (fbPower.Error OR fbEnable.Error OR fbStatus.GroupErrorStop OR xError) AND NOT xFault
   AND NOT xResetRequest THEN
    xFault := TRUE;
    IF eSmcError = SMC_ERROR.SMC_NO_ERROR THEN
        IF fbEnable.Error THEN eSmcError := fbEnable.ErrorID; ELSE eSmcError := fbPower.ErrorID; END_IF
    END_IF
    IF itfAlarms <> 0 THEN
        itfAlarms.Raise(E_AlarmId.AxisGroupError);
    END_IF
END_IF

xMoving := fbStatus.GroupMoving OR fbStatus.GroupStopping;
xReady := fbEnable.Done AND NOT xFault AND NOT fbStatus.GroupErrorStop;
