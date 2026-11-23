(*
    FB_SafetyMonitor
    Purpose : Modelled safety logic (not certified): E-stop latch and safety door per mode.
    Inputs  : xEStopOk (TRUE = not pressed), xDoorClosed, eMode, xResetCmd, itfAlarms
    Outputs : xSafeToMove - motion allowed; xReducedSpeed - only reduced speed allowed
    Rules   : E-stop latches until xEStopOk AND xResetCmd. Door open in Production or
              Maintenance -> not safe (DoorOpen). Door open in Manual -> safe, reduced speed.
    Alarms  : EStop, DoorOpen
*)
FUNCTION_BLOCK FB_SafetyMonitor
VAR_INPUT
    xEStopOk : BOOL := TRUE;
    xDoorClosed : BOOL := TRUE;
    eMode : E_PackMLMode := E_PackMLMode.Production;
    xResetCmd : BOOL;
    itfAlarms : I_AlarmSink;
END_VAR
VAR_OUTPUT
    xSafeToMove : BOOL;
    xReducedSpeed : BOOL;
END_VAR
VAR
    xEStopLatched : BOOL;
    xDoorFault : BOOL;
END_VAR

IF NOT xEStopOk THEN
    xEStopLatched := TRUE;
ELSIF xResetCmd THEN
    xEStopLatched := FALSE;
END_IF

xDoorFault := NOT xDoorClosed AND eMode <> E_PackMLMode.Manual;
xSafeToMove := NOT xEStopLatched AND NOT xDoorFault;
xReducedSpeed := NOT xDoorClosed AND eMode = E_PackMLMode.Manual;

IF itfAlarms <> 0 THEN
    IF xEStopLatched THEN
        itfAlarms.Raise(E_AlarmId.EStop);
    ELSE
        itfAlarms.Clear(E_AlarmId.EStop);
    END_IF
    IF xDoorFault THEN
        itfAlarms.Raise(E_AlarmId.DoorOpen);
    ELSE
        itfAlarms.Clear(E_AlarmId.DoorOpen);
    END_IF
END_IF
