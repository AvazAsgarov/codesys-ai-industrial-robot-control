// State of one alarm (for the HMI view).
METHOD AlarmState : ST_Alarm
VAR_INPUT
    eId : E_AlarmId;
END_VAR

AlarmState := fbAlarms.GetAlarm(eId);
