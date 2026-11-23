METHOD Raise
VAR_INPUT
    eId : E_AlarmId;
END_VAR

IF eId = E_AlarmId.None OR aAlarms[eId].xActive THEN
    RETURN;
END_IF
aAlarms[eId].eClass := GVL_AlarmDefs.aDefs[eId].eClass;
aAlarms[eId].xActive := TRUE;
aAlarms[eId].xAcked := FALSE;
aAlarms[eId].tRaised := TIME();
eNewest := eId;
