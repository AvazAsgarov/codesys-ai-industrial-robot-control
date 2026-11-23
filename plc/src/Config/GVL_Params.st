// Process parameters. Retained; written by the recipes (Standard / HighSpeed).
{attribute 'qualified_only'}
VAR_GLOBAL RETAIN
    lrBeltSpeed : LREAL := 100;              // conveyor speed [mm/s]
    lrApproachHeight : LREAL := 80;          // approach / lift height above the part [mm]
    lrPickDepth : LREAL := 5;                // how far below the part top the cup goes [mm]
    lrLinVelocity : LREAL := 500;            // linear path velocity [mm/s]
    lrLinAccel : LREAL := 2000;              // linear path acceleration [mm/s2]
    lrLinJerk : LREAL := 20000;              // linear path jerk [mm/s3]
    lrPtpVelFactor : LREAL := 0.5;           // PTP velocity factor ]0, 1]
    rConfidenceThreshold : REAL := 0.6;      // below this the part goes to quarantine
    tDecisionDeadline : TIME := T#2S500MS;   // fallback if no decision by then
    tVacuumTimeout : TIME := T#500MS;        // no grip -> error
    lrFollowErrWarn : LREAL := 2.0;          // following error warning [deg]
    lrFollowErrFault : LREAL := 5.0;         // following error fault [deg]
    tFeedbackTimeout : TIME := T#500MS;      // joint feedback must update within this time
    aClassToBin : ARRAY[0..2] OF E_Bin := [E_Bin.TypeA, E_Bin.TypeB, E_Bin.TypeC];
END_VAR
