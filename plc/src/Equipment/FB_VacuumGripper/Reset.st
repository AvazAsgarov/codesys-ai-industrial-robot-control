METHOD Reset : BOOL

IF itfAlarms <> 0 AND eError <> E_AlarmId.None THEN
    itfAlarms.Clear(eError);
END_IF
eError := E_AlarmId.None;
xWasHolding := FALSE;
Reset := TRUE;
