// Operator commands from the HMI.
{attribute 'qualified_only'}
VAR_GLOBAL
    eCommand : E_PackMLCommand;
    eModeRequest : E_PackMLMode := E_PackMLMode.Production;
    xAlarmAck : BOOL;
    axJogPlus : ARRAY[1..6] OF BOOL;
    axJogMinus : ARRAY[1..6] OF BOOL;
    rOverride : REAL := 1.0;                               // speed override ]0, 1]
END_VAR
