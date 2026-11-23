// Enter the error path: stop the robot first (Aborting), then rest in Error.
METHOD PRIVATE GoError

eStep := E_PickStep.Aborting;
xFaultPending := TRUE;
iCmdPhase := 0;
xRequested := FALSE;
