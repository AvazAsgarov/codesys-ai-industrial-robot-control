(*
    FB_BridgeWatchdog
    Purpose : The Python bridge toggles xHeartbeat every cycle; if it stops toggling for tTimeout
              while enabled, the connection to the digital twin is considered lost.
    Outputs : xLost
    Alarms  : BridgeLost (Critical -> the cell aborts)
*)
FUNCTION_BLOCK FB_BridgeWatchdog
VAR_INPUT
    xHeartbeat : BOOL;
    xEnable : BOOL;
    tTimeout : TIME := T#500MS;
    itfAlarms : I_AlarmSink;
END_VAR
VAR_OUTPUT
    xLost : BOOL;
END_VAR
VAR
    xLastHeartbeat : BOOL;
    tonLost : TON;
END_VAR

tonLost(IN := xEnable AND xHeartbeat = xLastHeartbeat, PT := tTimeout);
xLastHeartbeat := xHeartbeat;
xLost := tonLost.Q;
IF itfAlarms <> 0 THEN
    IF xLost THEN
        itfAlarms.Raise(E_AlarmId.BridgeLost);
    ELSE
        itfAlarms.Clear(E_AlarmId.BridgeLost);
    END_IF
END_IF
