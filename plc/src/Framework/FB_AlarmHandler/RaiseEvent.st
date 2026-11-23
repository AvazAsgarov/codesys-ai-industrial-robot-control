METHOD RaiseEvent
VAR_INPUT
    eId : E_AlarmId;
END_VAR

IF eId = E_AlarmId.None THEN
    RETURN;
END_IF
aAlarms[eId].eClass := GVL_AlarmDefs.aDefs[eId].eClass;
aAlarms[eId].xActive := FALSE;
aAlarms[eId].xAcked := FALSE;
aAlarms[eId].tRaised := TIME();
eNewest := eId;
