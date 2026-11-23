// Requests a robot command once per step; the handshake in the body executes it.
METHOD PRIVATE Request
VAR_INPUT
    eCmd : E_RobotCmd;
    stTgt : SMC_POS_REF;
END_VAR

IF NOT xRequested AND iCmdPhase = 0 THEN
    eReqCmd := eCmd;
    stReqTarget := stTgt;
    iCmdPhase := 1;
    xRequested := TRUE;
END_IF
