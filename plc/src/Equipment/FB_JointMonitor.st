(*
    FB_JointMonitor
    Purpose : Supervises the robot joints against the feedback of the digital twin's servo
              motors: following error per joint and freshness of the feedback.
    Inputs  : aSetpoint / aFeedback [deg], aTorque [Nm], udiFeedbackSeq (changes with every new
              feedback sample), udiSetpointSeq (number of the current setpoint sample, +1 per
              cycle), udiFeedbackForSeq (setpoint sample the feedback answers), xLoopback
              (feedback := setpoint, no staleness check), xActive (supervision on), itfAlarms
    Outputs : aFollowingError [deg], iWorstJoint (1..6, 0 = none), xWarn, xFault, xStale
    Latency : the feedback travels through OPC UA and the twin (tens of ms). The last
              HISTORY_SIZE setpoints are kept, and the feedback is compared with the setpoint it
              answers, so transport delay does not count as following error; a feedback older
              than the history is compared with the current setpoint.
    Debounce: a following error counts after CONFIRM_CYCLES cycles in a row. OPC UA does not
              hand a write to the task atomically: for one cycle the new positions may meet the
              old sequence number (a torn sample), which must not abort the cell.
    Limits  : GVL_Params.lrFollowErrWarn / lrFollowErrFault / tFeedbackTimeout
    Alarms  : FollowingErrorWarn, FollowingErrorFault, FeedbackStale
*)
FUNCTION_BLOCK FB_JointMonitor
VAR_INPUT
    aSetpoint : ARRAY[1..6] OF LREAL;
    aFeedback : ARRAY[1..6] OF LREAL;
    aTorque : ARRAY[1..6] OF LREAL;
    udiFeedbackSeq : UDINT;
    udiSetpointSeq : UDINT;
    udiFeedbackForSeq : UDINT;
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
    aHistory : ARRAY[0..HISTORY_SIZE - 1, 1..6] OF LREAL;
    udiSlot : UDINT;
    xFromHistory : BOOL;
    uiWarnCycles : UINT;
    uiFaultCycles : UINT;
END_VAR
VAR CONSTANT
    HISTORY_SIZE : UDINT := 128;            // setpoint samples kept (512 ms at 4 ms)
    CONFIRM_CYCLES : UINT := 3;             // following error must persist this long (12 ms)
END_VAR

udiSlot := udiSetpointSeq MOD HISTORY_SIZE;
FOR i := 1 TO 6 DO
    aHistory[udiSlot, i] := aSetpoint[i];
END_FOR
// UDINT arithmetic: a feedback that answers a future setpoint wraps to a large age.
xFromHistory := udiSetpointSeq - udiFeedbackForSeq < HISTORY_SIZE;
udiSlot := udiFeedbackForSeq MOD HISTORY_SIZE;

lrWorst := 0;
iWorstJoint := 0;
FOR i := 1 TO 6 DO
    IF xLoopback THEN
        aFollowingError[i] := 0;
    ELSIF xFromHistory THEN
        aFollowingError[i] := ABS(aHistory[udiSlot, i] - aFeedback[i]);
    ELSE
        aFollowingError[i] := ABS(aSetpoint[i] - aFeedback[i]);
    END_IF
    IF aFollowingError[i] > lrWorst THEN
        lrWorst := aFollowingError[i];
        iWorstJoint := i;
    END_IF
END_FOR

IF xActive AND lrWorst > GVL_Params.lrFollowErrWarn THEN
    uiWarnCycles := MIN(uiWarnCycles + 1, CONFIRM_CYCLES);
ELSE
    uiWarnCycles := 0;
END_IF
IF xActive AND lrWorst > GVL_Params.lrFollowErrFault THEN
    uiFaultCycles := MIN(uiFaultCycles + 1, CONFIRM_CYCLES);
ELSE
    uiFaultCycles := 0;
END_IF
xWarn := uiWarnCycles >= CONFIRM_CYCLES;
xFault := uiFaultCycles >= CONFIRM_CYCLES;

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
