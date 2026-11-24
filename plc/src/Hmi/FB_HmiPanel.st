(*
    FB_HmiPanel
    Purpose : Turns the operator panel (GVL_HmiPanel: buttons, mode selector) into the cell's
              commands (GVL_Hmi). A button acts on its rising edge and is cleared, so a held or
              stuck button cannot repeat a command; the PackML state machine rejects commands
              that are not allowed in the current state.
    Inputs  : GVL_HmiPanel (written by the visualization), GVL_Bridge.eState
    Outputs : GVL_Hmi.eCommand / eModeRequest / xAlarmAck
    Modes   : iModeSelect 1 Production, 2 Maintenance, 3 Manual; other values are ignored. An
              operator change is requested only where PackML accepts a mode change (Stopped,
              Idle, Aborted), so no request waits to take effect after a later abort. The
              selector then shows GVL_Hmi.eModeRequest, whoever wrote it (panel or OPC UA).
*)
FUNCTION_BLOCK FB_HmiPanel
VAR
    rtStart : R_TRIG;
    rtStop : R_TRIG;
    rtReset : R_TRIG;
    rtClear : R_TRIG;
    rtAbort : R_TRIG;
    rtSuspend : R_TRIG;
    rtUnsuspend : R_TRIG;
    rtAck : R_TRIG;
    iLastMode : INT := 1;  // the selector value the panel showed last cycle
    xModeChangeAllowed : BOOL;
END_VAR

rtStart(CLK := GVL_HmiPanel.xStart);
rtStop(CLK := GVL_HmiPanel.xStop);
rtReset(CLK := GVL_HmiPanel.xReset);
rtClear(CLK := GVL_HmiPanel.xClear);
rtAbort(CLK := GVL_HmiPanel.xAbort);
rtSuspend(CLK := GVL_HmiPanel.xSuspend);
rtUnsuspend(CLK := GVL_HmiPanel.xUnsuspend);
rtAck(CLK := GVL_HmiPanel.xAckAll);

// Abort and Stop first: a safety-relevant command wins over a start in the same cycle.
IF rtAbort.Q THEN
    GVL_Hmi.eCommand := E_PackMLCommand.Abort;
ELSIF rtStop.Q THEN
    GVL_Hmi.eCommand := E_PackMLCommand.Stop;
ELSIF rtClear.Q THEN
    GVL_Hmi.eCommand := E_PackMLCommand.Clear;
ELSIF rtReset.Q THEN
    GVL_Hmi.eCommand := E_PackMLCommand.Reset;
ELSIF rtSuspend.Q THEN
    GVL_Hmi.eCommand := E_PackMLCommand.Suspend;
ELSIF rtUnsuspend.Q THEN
    GVL_Hmi.eCommand := E_PackMLCommand.Unsuspend;
ELSIF rtStart.Q THEN
    GVL_Hmi.eCommand := E_PackMLCommand.Start;
END_IF
IF rtAck.Q THEN
    GVL_Hmi.xAlarmAck := TRUE;
END_IF

// mode selector: an operator change, only where PackML accepts it
IF GVL_HmiPanel.iModeSelect <> iLastMode THEN
    xModeChangeAllowed := GVL_Bridge.eState = E_PackMLState.Stopped
                          OR GVL_Bridge.eState = E_PackMLState.Idle
                          OR GVL_Bridge.eState = E_PackMLState.Aborted;
    IF xModeChangeAllowed THEN
        CASE GVL_HmiPanel.iModeSelect OF
            1: GVL_Hmi.eModeRequest := E_PackMLMode.Production;
            2: GVL_Hmi.eModeRequest := E_PackMLMode.Maintenance;
            3: GVL_Hmi.eModeRequest := E_PackMLMode.Manual;
        END_CASE   // other values: ignored
    END_IF
END_IF
// the selector shows the request (refused or invalid choices fall back, OPC UA requests show)
CASE GVL_Hmi.eModeRequest OF
    E_PackMLMode.Production: iLastMode := 1;
    E_PackMLMode.Maintenance: iLastMode := 2;
    E_PackMLMode.Manual: iLastMode := 3;
END_CASE
GVL_HmiPanel.iModeSelect := iLastMode;

GVL_HmiPanel.xStart := FALSE;
GVL_HmiPanel.xStop := FALSE;
GVL_HmiPanel.xReset := FALSE;
GVL_HmiPanel.xClear := FALSE;
GVL_HmiPanel.xAbort := FALSE;
GVL_HmiPanel.xSuspend := FALSE;
GVL_HmiPanel.xUnsuspend := FALSE;
GVL_HmiPanel.xAckAll := FALSE;
