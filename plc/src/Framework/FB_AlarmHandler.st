(*
    FB_AlarmHandler
    Purpose : Latching alarm list (ISA-18.2 style): an alarm needs both its condition gone
              (Clear) and an acknowledgement before it leaves the list.
    Methods : Raise(eId), Clear(eId) (I_AlarmSink), AcknowledgeAll(), GetAlarm(eId)
    Outputs : xCriticalActive / xErrorActive / xWarningActive - an alarm of that class is
              active OR unacknowledged; uiActiveCount - conditions currently active;
              eNewest - last raised alarm
    Call    : the FB body once per cycle after the Raise/Clear calls of that cycle
*)
FUNCTION_BLOCK FB_AlarmHandler IMPLEMENTS I_AlarmSink
VAR_OUTPUT
    xCriticalActive : BOOL;
    xErrorActive : BOOL;
    xWarningActive : BOOL;
    uiActiveCount : UINT;
    eNewest : E_AlarmId;
END_VAR
VAR
    aAlarms : ARRAY[E_AlarmId.None..E_AlarmId.QueueOverflow] OF ST_Alarm;
    eId : E_AlarmId;
END_VAR

xCriticalActive := FALSE;
xErrorActive := FALSE;
xWarningActive := FALSE;
uiActiveCount := 0;
FOR eId := E_AlarmId.EStop TO E_AlarmId.QueueOverflow DO
    IF aAlarms[eId].xActive THEN
        uiActiveCount := uiActiveCount + 1;
    END_IF
    IF aAlarms[eId].xActive OR NOT aAlarms[eId].xAcked THEN
        CASE GVL_AlarmDefs.aDefs[eId].eClass OF
            E_AlarmClass.Critical: xCriticalActive := TRUE;
            E_AlarmClass.Error: xErrorActive := TRUE;
            E_AlarmClass.Warning: xWarningActive := TRUE;
        END_CASE
    END_IF
END_FOR
