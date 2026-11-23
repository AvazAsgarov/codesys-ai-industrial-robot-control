// Requests an axis group reset (done in the next FB calls). Returns TRUE when error-free.
METHOD Reset : BOOL

IF xFault THEN
    xResetRequest := TRUE;
END_IF
Reset := NOT xFault;
