(*
    FB_VacuumGripper
    Purpose : Suction gripper: valve control with grip and loss supervision.
    Inputs  : xCmdVacuum, xVacuumOk (vacuum switch), tGripTimeout, itfAlarms
    Outputs : xValveOn, xHolding (vacuum on and OK)
    Errors  : VacuumNoGrip - commanded but not OK within tGripTimeout
              VacuumLost - was holding and lost vacuum while still commanded
*)
FUNCTION_BLOCK FB_VacuumGripper IMPLEMENTS I_Equipment
VAR_INPUT
    xCmdVacuum : BOOL;
    xVacuumOk : BOOL;
    tGripTimeout : TIME := T#500MS;
    itfAlarms : I_AlarmSink;
END_VAR
VAR_OUTPUT
    xValveOn : BOOL;
    xHolding : BOOL;
END_VAR
VAR
    tonGrip : TON;
    xWasHolding : BOOL;
    eError : E_AlarmId;
END_VAR

xValveOn := xCmdVacuum;
xHolding := xCmdVacuum AND xVacuumOk;

tonGrip(IN := xCmdVacuum AND NOT xVacuumOk AND NOT xWasHolding, PT := tGripTimeout);
IF tonGrip.Q AND eError = E_AlarmId.None THEN
    eError := E_AlarmId.VacuumNoGrip;
END_IF
IF xWasHolding AND xCmdVacuum AND NOT xVacuumOk AND eError = E_AlarmId.None THEN
    eError := E_AlarmId.VacuumLost;
END_IF

IF xHolding THEN
    xWasHolding := TRUE;
ELSIF NOT xCmdVacuum THEN
    xWasHolding := FALSE;
END_IF

IF eError <> E_AlarmId.None AND itfAlarms <> 0 THEN
    itfAlarms.Raise(eError);
END_IF
