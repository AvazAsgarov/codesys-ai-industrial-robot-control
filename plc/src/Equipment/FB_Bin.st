(*
    FB_Bin
    Purpose : Output bin: counts placed parts and reports the full sensor.
    Inputs  : eBin - which bin; xFullSensor; xPlaced - rising edge = one part placed
    Outputs : uiCount, xFull
    Methods : Empty() - operator emptied the bin
*)
FUNCTION_BLOCK FB_Bin
VAR_INPUT
    eBin : E_Bin;
    xFullSensor : BOOL;
    xPlaced : BOOL;
END_VAR
VAR_OUTPUT
    uiCount : UINT;
    xFull : BOOL;
END_VAR
VAR
    rtPlaced : R_TRIG;
END_VAR

rtPlaced(CLK := xPlaced);
IF rtPlaced.Q THEN
    uiCount := uiCount + 1;
END_IF
xFull := xFullSensor;
