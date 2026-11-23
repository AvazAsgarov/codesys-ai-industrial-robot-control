(*
    FB_PhotoEye
    Purpose : Debounced photo-eye with a rising-edge pulse.
    Inputs  : xRaw - sensor signal (TRUE = beam blocked); tDebounce - on/off filter time
    Outputs : xBlocked - debounced state; xRising - TRUE for one cycle when it becomes blocked
*)
FUNCTION_BLOCK FB_PhotoEye
VAR_INPUT
    xRaw : BOOL;
    tDebounce : TIME := T#10MS;
END_VAR
VAR_OUTPUT
    xBlocked : BOOL;
    xRising : BOOL;
END_VAR
VAR
    tonOn : TON;
    tonOff : TON;
END_VAR

tonOn(IN := xRaw, PT := tDebounce);
tonOff(IN := NOT xRaw, PT := tDebounce);
xRising := FALSE;
IF tonOn.Q AND NOT xBlocked THEN
    xBlocked := TRUE;
    xRising := TRUE;
ELSIF tonOff.Q THEN
    xBlocked := FALSE;
END_IF
