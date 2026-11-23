// Acknowledge every alarm. Active alarms stay listed until their condition clears.
METHOD AcknowledgeAll
VAR
    eId : E_AlarmId;
END_VAR

FOR eId := E_AlarmId.EStop TO E_AlarmId.QueueOverflow DO
    aAlarms[eId].xAcked := TRUE;
END_FOR
