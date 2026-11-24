// Operator panel of the CODESYS Visualization: buttons and selectors write here; FB_HmiPanel
// turns them into the cell's commands (GVL_Hmi). Buttons are one-shot: cleared after use.
{attribute 'qualified_only'}
VAR_GLOBAL
    xStart : BOOL;
    xStop : BOOL;
    xReset : BOOL;
    xClear : BOOL;
    xAbort : BOOL;
    xSuspend : BOOL;
    xUnsuspend : BOOL;
    xAckAll : BOOL;                                        // acknowledge all alarms
    iModeSelect : INT := 1;                                // 1 Production, 2 Maintenance, 3 Manual
END_VAR
