VAR
END_VAR

IF xFault THEN
    ErrorId := E_AlarmId.AxisGroupError;
ELSE
    ErrorId := E_AlarmId.None;
END_IF
