(*
    PRG_TestTracking
    Purpose : Simulation test harness for FB_PartTracker and F_SelectBin (tests/plc/tracking.json).
    Inputs  : lrBeltPos; xTriggerPE1 (one capture); uiFillCount (that many captures, one per cycle);
              stVisIn + xSendVision / xResendVision (same sequence number again);
              stDecIn + xSendDecision; udiQueryId - part to show in stRec; xAck
    Outputs : uiCount, uiNext (next pickable index), stRec, xQueryFound
*)
PROGRAM PRG_TestTracking
VAR
    fbTracker : FB_PartTracker;
    fbAlarms : FB_AlarmHandler;
    fbTrackerInitial : FB_PartTracker;
    fbAlarmsInitial : FB_AlarmHandler;
    xReinit : BOOL;
    lrBeltPos : LREAL;
    xTriggerPE1 : BOOL;
    uiFillCount : UINT;
    stVisIn : ST_VisionMsg;
    stDecIn : ST_DecisionMsg;
    xSendVision : BOOL;
    xResendVision : BOOL;
    xSendDecision : BOOL;
    xAck : BOOL;
    udiVisionSeq : UDINT;
    udiDecisionSeq : UDINT;
    udiQueryId : UDINT;
    uiQueryIdx : UINT;
    xQueryFound : BOOL;
    stRec : ST_PartRecord;
    uiCount : UINT;
    uiNext : UINT;
    xPE1Rising : BOOL;
END_VAR

IF xReinit THEN
    xReinit := FALSE;
    fbTracker := fbTrackerInitial;
    fbAlarms := fbAlarmsInitial;
    udiVisionSeq := 0;
    udiDecisionSeq := 0;
    uiFillCount := 0;
END_IF

xPE1Rising := xTriggerPE1 OR uiFillCount > 0;
xTriggerPE1 := FALSE;
IF uiFillCount > 0 THEN
    uiFillCount := uiFillCount - 1;
END_IF

IF xSendVision THEN
    xSendVision := FALSE;
    udiVisionSeq := udiVisionSeq + 1;
END_IF
IF xResendVision THEN
    xResendVision := FALSE;      // same sequence number: must be ignored
END_IF
stVisIn.udiSeq := udiVisionSeq;
IF xSendDecision THEN
    xSendDecision := FALSE;
    udiDecisionSeq := udiDecisionSeq + 1;
END_IF
stDecIn.udiSeq := udiDecisionSeq;
IF xAck THEN
    xAck := FALSE;
    fbAlarms.AcknowledgeAll();
END_IF

fbTracker.itfAlarms := fbAlarms;
fbTracker(lrBeltPos := lrBeltPos, xPE1Rising := xPE1Rising, stVision := stVisIn, stDecision := stDecIn);
fbAlarms();

uiCount := fbTracker.Count;
uiNext := fbTracker.NextPickable(GVL_CellGeometry.PE2_X, GVL_CellGeometry.PICK_WINDOW_END_X);
uiQueryIdx := fbTracker.FindPart(udiQueryId);
xQueryFound := uiQueryIdx > 0;
IF xQueryFound THEN
    stRec := fbTracker.GetRecord(uiQueryIdx);
END_IF
