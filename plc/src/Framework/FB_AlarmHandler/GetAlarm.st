METHOD GetAlarm : ST_Alarm
VAR_INPUT
    eId : E_AlarmId;
END_VAR

GetAlarm := aAlarms[eId];
