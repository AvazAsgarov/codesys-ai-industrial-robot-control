TYPE ST_Recipe_Cell :
STRUCT
    lrBeltSpeed : LREAL; // GVL_Params.lrBeltSpeed
    lrApproachHeight : LREAL; // GVL_Params.lrApproachHeight
    lrPickDepth : LREAL; // GVL_Params.lrPickDepth
    lrLinVelocity : LREAL; // GVL_Params.lrLinVelocity
    lrLinAccel : LREAL; // GVL_Params.lrLinAccel
    lrLinJerk : LREAL; // GVL_Params.lrLinJerk
    lrPtpVelFactor : LREAL; // GVL_Params.lrPtpVelFactor
    rConfidenceThreshold : REAL; // GVL_Params.rConfidenceThreshold
    tDecisionDeadline : TIME; // GVL_Params.tDecisionDeadline
    tVacuumTimeout : TIME; // GVL_Params.tVacuumTimeout
    lrFollowErrWarn : LREAL; // GVL_Params.lrFollowErrWarn
    lrFollowErrFault : LREAL; // GVL_Params.lrFollowErrFault
    tFeedbackTimeout : TIME; // GVL_Params.tFeedbackTimeout
END_STRUCT
END_TYPE
