// Requests an axis reset (done in the next FB calls). Returns TRUE when already error-free.
METHOD Reset : BOOL

IF eError <> E_AlarmId.None THEN
    xResetRequest := TRUE;
END_IF
Reset := eError = E_AlarmId.None;
