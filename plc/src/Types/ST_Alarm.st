// Runtime state of one alarm.
TYPE ST_Alarm :
STRUCT
    eClass : E_AlarmClass;
    xActive : BOOL;
    xAcked : BOOL := TRUE;              // no pending acknowledgement
    tRaised : TIME;
END_STRUCT
END_TYPE
