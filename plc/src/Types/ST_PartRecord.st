// One tracked part. Positions are in the belt frame at capture time (mm, degrees).
TYPE ST_PartRecord :
STRUCT
    udiPartId : UDINT;
    lrBeltPosAtCapture : LREAL;         // conveyor axis position when PE1 triggered [mm]
    xVisionValid : BOOL;
    usiClass : USINT;                   // detector class index 0..2
    rConfidence : REAL;                 // detector confidence 0..1
    lrX : LREAL;                        // belt frame X at capture [mm]
    lrY : LREAL;                        // belt frame Y [mm]
    lrTheta : LREAL;                    // orientation about Z [deg]
    eQuality : E_Quality;
    rQualityProb : REAL;                // probability of the chosen quality option
    xIdentReliable : BOOL;
    eDecisionSource : E_DecisionSource;
    eTargetBin : E_Bin;
    eState : E_PartState;
    tCaptured : TIME;                   // TIME() at capture
END_STRUCT
END_TYPE
