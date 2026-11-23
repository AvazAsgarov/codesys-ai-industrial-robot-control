// Vision result written by the bridge. A new message has a new udiSeq.
TYPE ST_VisionMsg :
STRUCT
    udiSeq : UDINT;
    udiPartId : UDINT;
    xValid : BOOL;
    usiClass : USINT;
    rConfidence : REAL;
    lrX : LREAL;                        // belt frame [mm]
    lrY : LREAL;                        // belt frame [mm]
    lrTheta : LREAL;                    // [deg]
END_STRUCT
END_TYPE
