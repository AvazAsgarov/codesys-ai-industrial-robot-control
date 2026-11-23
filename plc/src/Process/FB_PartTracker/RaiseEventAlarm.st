METHOD PRIVATE RaiseEventAlarm
VAR_INPUT
    eId : E_AlarmId;
END_VAR

IF itfAlarms <> 0 THEN
    itfAlarms.RaiseEvent(eId);
END_IF
