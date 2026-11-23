(*
    FB_JointMonitor
    Purpose : Supervises the robot joints against the feedback of the digital twin's servo
              motors: following error per joint and freshness of the feedback.
    Inputs  : aSetpoint / aFeedback [deg], aTorque [Nm], udiFeedbackSeq (changes with every new
              feedback sample), xLoopback (feedback := setpoint, no staleness check),
              xActive (supervision on), itfAlarms
    Outputs : aFollowingError [deg], iWorstJoint (1..6, 0 = none), xWarn, xFault, xStale
    Limits  : GVL_Params.lrFollowErrWarn / lrFollowErrFault / tFeedbackTimeout
    Alarms  : FollowingErrorWarn, FollowingErrorFault, FeedbackStale
*)
FUNCTION_BLOCK FB_JointMonitor
VAR_INPUT
    aSetpoint : ARRAY[1..6] OF LREAL;
    aFeedback : ARRAY[1..6] OF LREAL;
    aTorque : ARRAY[1..6] OF LREAL;
    udiFeedbackSeq : UDINT;
    xLoopback : BOOL;
    xActive : BOOL;
    itfAlarms : I_AlarmSink;
END_VAR
VAR_OUTPUT
    aFollowingError : ARRAY[1..6] OF LREAL;
    iWorstJoint : INT;
    xWarn : BOOL;
    xFault : BOOL;
    xStale : BOOL;
END_VAR
VAR
    i : INT;
    lrWorst : LREAL;
    udiLastSeq : UDINT;
    tonStale : TON;
END_VAR

lrWorst := 0;
iWorstJoint := 0;
FOR i := 1 TO 6 DO
    IF xLoopback THEN
        aFollowingError[i] := 0;
    ELSE
        aFollowingError[i] := ABS(aSetpoint[i] - aFeedback[i]);
    END_IF
    IF aFollowingError[i] > lrWorst THEN
        lrWorst := aFollowingError[i];
        iWorstJoint := i;
    END_IF
END_FOR

xWarn := xActive AND lrWorst > GVL_Params.lrFollowErrWarn;
xFault := xActive AND lrWorst > GVL_Params.lrFollowErrFault;

// Feedback must keep arriving while supervised (not in loopback).
tonStale(IN := xActive AND NOT xLoopback AND udiFeedbackSeq = udiLastSeq, PT := GVL_Params.tFeedbackTimeout);
udiLastSeq := udiFeedbackSeq;
xStale := tonStale.Q;
xFault := xFault OR xStale;

IF itfAlarms <> 0 THEN
    IF xWarn THEN itfAlarms.Raise(E_AlarmId.FollowingErrorWarn); ELSE itfAlarms.Clear(E_AlarmId.FollowingErrorWarn); END_IF
    IF xFault AND NOT xStale THEN itfAlarms.Raise(E_AlarmId.FollowingErrorFault); ELSE itfAlarms.Clear(E_AlarmId.FollowingErrorFault); END_IF
    IF xStale THEN itfAlarms.Raise(E_AlarmId.FeedbackStale); ELSE itfAlarms.Clear(E_AlarmId.FeedbackStale); END_IF
END_IF
