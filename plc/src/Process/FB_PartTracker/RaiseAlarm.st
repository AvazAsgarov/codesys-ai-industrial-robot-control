METHOD PRIVATE RaiseAlarm
VAR_INPUT
    eId : E_AlarmId;
END_VAR

IF itfAlarms <> 0 THEN
    itfAlarms.Raise(eId);
END_IF
