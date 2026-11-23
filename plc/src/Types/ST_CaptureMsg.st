// Capture request from the PLC to the bridge. A new request has a new udiSeq.
TYPE ST_CaptureMsg :
STRUCT
    udiSeq : UDINT;
    udiPartId : UDINT;
    lrBeltPos : LREAL;                  // conveyor axis position at the trigger [mm]
END_STRUCT
END_TYPE
