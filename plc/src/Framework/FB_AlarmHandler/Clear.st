METHOD Clear
VAR_INPUT
    eId : E_AlarmId;
END_VAR

aAlarms[eId].xActive := FALSE;
