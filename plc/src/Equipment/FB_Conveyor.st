(*
    FB_Conveyor
    Purpose : Conveyor belt on a SoftMotion axis: power, run at a velocity, halt, read back.
    In/Out  : Axis - the conveyor axis (Axis_Conveyor)
    Inputs  : xEnable - power; lrVelocity - belt speed [mm/s]; xRun - move (FALSE = halt)
    Outputs : xPowered, xAtSpeed, lrPosition [mm], lrActVelocity [mm/s]
    Alarms  : ConveyorError
*)
FUNCTION_BLOCK FB_Conveyor IMPLEMENTS I_Equipment
VAR_IN_OUT
    Axis : AXIS_REF_SM3;
END_VAR
VAR_INPUT
    xEnable : BOOL;
    lrVelocity : LREAL;
    xRun : BOOL;
    itfAlarms : I_AlarmSink;
END_VAR
VAR_OUTPUT
    xPowered : BOOL;
    xAtSpeed : BOOL;
    lrPosition : LREAL;
    lrActVelocity : LREAL;
END_VAR
VAR
    fbPower : MC_Power;
    fbMove : MC_MoveVelocity;
    fbHalt : MC_Halt;
    fbReset : MC_Reset;
    fbReadPos : MC_ReadActualPosition;
    fbReadVel : MC_ReadActualVelocity;
    lrLastVelocity : LREAL;
    xRestart : BOOL;
    xResetRequest : BOOL;
    eError : E_AlarmId;
END_VAR
VAR CONSTANT
    ACCELERATION : LREAL := 1000;      // [mm/s2]
    JERK : LREAL := 10000;             // [mm/s3]
END_VAR

fbPower(Axis := Axis, Enable := xEnable, bRegulatorOn := xEnable, bDriveStart := xEnable);
xPowered := fbPower.Status;

// A changed velocity needs a new rising edge on Execute: drop it for one cycle.
xRestart := xRun AND lrVelocity <> lrLastVelocity;
lrLastVelocity := lrVelocity;
fbMove(Axis := Axis,
       Execute := xRun AND xPowered AND NOT xRestart AND eError = E_AlarmId.None,
       Velocity := ABS(lrVelocity),
       Acceleration := ACCELERATION,
       Deceleration := ACCELERATION,
       Jerk := JERK,
       Direction := MC_Direction.positive);
fbHalt(Axis := Axis, Execute := NOT xRun AND xPowered, Deceleration := ACCELERATION, Jerk := JERK);
xAtSpeed := fbMove.InVelocity;

fbReadPos(Axis := Axis, Enable := TRUE);
fbReadVel(Axis := Axis, Enable := TRUE);
lrPosition := fbReadPos.Position;
lrActVelocity := fbReadVel.Velocity;

IF (fbPower.Error OR fbMove.Error OR fbHalt.Error) AND eError = E_AlarmId.None THEN
    eError := E_AlarmId.ConveyorError;
    IF itfAlarms <> 0 THEN
        itfAlarms.Raise(eError);
    END_IF
END_IF

fbReset(Axis := Axis, Execute := xResetRequest);
IF xResetRequest AND (fbReset.Done OR fbReset.Error) THEN
    xResetRequest := FALSE;
    IF fbReset.Done THEN
        IF itfAlarms <> 0 AND eError <> E_AlarmId.None THEN
            itfAlarms.Clear(eError);
        END_IF
        eError := E_AlarmId.None;
    END_IF
END_IF
