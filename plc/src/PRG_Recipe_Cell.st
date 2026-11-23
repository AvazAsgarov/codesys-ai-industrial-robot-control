PROGRAM PRG_Recipe_Cell
// Set iApply to a recipe's index to write it to the variables; set iSave to store the variables in it.
VAR
    iApply : INT := -1;
    iSave : INT := -1;
    iActive : INT := -1; // the recipe applied last
    sActive : STRING(32);
    p0 : POINTER TO LREAL; // GVL_Params.lrBeltSpeed
    p1 : POINTER TO LREAL; // GVL_Params.lrApproachHeight
    p2 : POINTER TO LREAL; // GVL_Params.lrPickDepth
    p3 : POINTER TO LREAL; // GVL_Params.lrLinVelocity
    p4 : POINTER TO LREAL; // GVL_Params.lrLinAccel
    p5 : POINTER TO LREAL; // GVL_Params.lrLinJerk
    p6 : POINTER TO LREAL; // GVL_Params.lrPtpVelFactor
    p7 : POINTER TO REAL; // GVL_Params.rConfidenceThreshold
    p8 : POINTER TO TIME; // GVL_Params.tDecisionDeadline
    p9 : POINTER TO TIME; // GVL_Params.tVacuumTimeout
    p10 : POINTER TO LREAL; // GVL_Params.lrFollowErrWarn
    p11 : POINTER TO LREAL; // GVL_Params.lrFollowErrFault
    p12 : POINTER TO TIME; // GVL_Params.tFeedbackTimeout
END_VAR

p0 := ADR(GVL_Params.lrBeltSpeed);
p1 := ADR(GVL_Params.lrApproachHeight);
p2 := ADR(GVL_Params.lrPickDepth);
p3 := ADR(GVL_Params.lrLinVelocity);
p4 := ADR(GVL_Params.lrLinAccel);
p5 := ADR(GVL_Params.lrLinJerk);
p6 := ADR(GVL_Params.lrPtpVelFactor);
p7 := ADR(GVL_Params.rConfidenceThreshold);
p8 := ADR(GVL_Params.tDecisionDeadline);
p9 := ADR(GVL_Params.tVacuumTimeout);
p10 := ADR(GVL_Params.lrFollowErrWarn);
p11 := ADR(GVL_Params.lrFollowErrFault);
p12 := ADR(GVL_Params.tFeedbackTimeout);
IF iApply >= 0 AND iApply < 2 THEN
    p0^ := GVL_Recipe_Cell.aRecipes[iApply].lrBeltSpeed;
    p1^ := GVL_Recipe_Cell.aRecipes[iApply].lrApproachHeight;
    p2^ := GVL_Recipe_Cell.aRecipes[iApply].lrPickDepth;
    p3^ := GVL_Recipe_Cell.aRecipes[iApply].lrLinVelocity;
    p4^ := GVL_Recipe_Cell.aRecipes[iApply].lrLinAccel;
    p5^ := GVL_Recipe_Cell.aRecipes[iApply].lrLinJerk;
    p6^ := GVL_Recipe_Cell.aRecipes[iApply].lrPtpVelFactor;
    p7^ := GVL_Recipe_Cell.aRecipes[iApply].rConfidenceThreshold;
    p8^ := GVL_Recipe_Cell.aRecipes[iApply].tDecisionDeadline;
    p9^ := GVL_Recipe_Cell.aRecipes[iApply].tVacuumTimeout;
    p10^ := GVL_Recipe_Cell.aRecipes[iApply].lrFollowErrWarn;
    p11^ := GVL_Recipe_Cell.aRecipes[iApply].lrFollowErrFault;
    p12^ := GVL_Recipe_Cell.aRecipes[iApply].tFeedbackTimeout;
    iActive := iApply;
    sActive := GVL_Recipe_Cell.asNames[iApply];
END_IF
iApply := -1;
IF iSave >= 0 AND iSave < 2 THEN
    GVL_Recipe_Cell.aRecipes[iSave].lrBeltSpeed := p0^;
    GVL_Recipe_Cell.aRecipes[iSave].lrApproachHeight := p1^;
    GVL_Recipe_Cell.aRecipes[iSave].lrPickDepth := p2^;
    GVL_Recipe_Cell.aRecipes[iSave].lrLinVelocity := p3^;
    GVL_Recipe_Cell.aRecipes[iSave].lrLinAccel := p4^;
    GVL_Recipe_Cell.aRecipes[iSave].lrLinJerk := p5^;
    GVL_Recipe_Cell.aRecipes[iSave].lrPtpVelFactor := p6^;
    GVL_Recipe_Cell.aRecipes[iSave].rConfidenceThreshold := p7^;
    GVL_Recipe_Cell.aRecipes[iSave].tDecisionDeadline := p8^;
    GVL_Recipe_Cell.aRecipes[iSave].tVacuumTimeout := p9^;
    GVL_Recipe_Cell.aRecipes[iSave].lrFollowErrWarn := p10^;
    GVL_Recipe_Cell.aRecipes[iSave].lrFollowErrFault := p11^;
    GVL_Recipe_Cell.aRecipes[iSave].tFeedbackTimeout := p12^;
END_IF
iSave := -1;
