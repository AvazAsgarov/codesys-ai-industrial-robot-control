(*
    FB_CameraTrigger
    Purpose : On the PE1 photo-eye edge, assigns a new part id and publishes a capture request
              (with the conveyor position) for the vision service.
    Outputs : stCapture (udiSeq increments per request), xNewPart (one cycle), udiNewPartId
*)
FUNCTION_BLOCK FB_CameraTrigger
VAR_INPUT
    xPE1Rising : BOOL;
    lrBeltPos : LREAL;
END_VAR
VAR_OUTPUT
    stCapture : ST_CaptureMsg;
    xNewPart : BOOL;
    udiNewPartId : UDINT;
END_VAR

xNewPart := xPE1Rising;
IF xPE1Rising THEN
    udiNewPartId := udiNewPartId + 1;
    stCapture.udiSeq := stCapture.udiSeq + 1;
    stCapture.udiPartId := udiNewPartId;
    stCapture.lrBeltPos := lrBeltPos;
END_IF
