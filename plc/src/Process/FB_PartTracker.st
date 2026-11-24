(*
    FB_PartTracker
    Purpose : Tracks every part from the PE1 capture until it is placed, missed or dropped.
              Applies vision and decision messages (only for known part ids, each message once),
              falls back to the rule-based decision at GVL_Params.tDecisionDeadline and marks
              parts that leave the pick window as missed.
    Inputs  : lrBeltPos [mm], xPE1Rising, stVision, stDecision, itfAlarms, xDecisionActive
    Outputs : stCapture (capture request to the vision service), udiPlaced/udiMissed/udiDropped,
              udiVisionMsgs (vision results applied)
    Methods : NextPickable, FindPart, GetRecord, SetState, CurrentX; property Count
    Belt X  : current X of a part = lrX (belt frame at capture) + (lrBeltPos - lrBeltPosAtCapture)
    Alarms  : QueueOverflow (condition: raised while full, cleared on the next successful capture);
              DecisionFallback, VisionMissing, LowConfidence, PartMissed (one-shot events)
*)
FUNCTION_BLOCK FB_PartTracker
VAR_INPUT
    lrBeltPos : LREAL;
    xPE1Rising : BOOL;
    stVision : ST_VisionMsg;
    stDecision : ST_DecisionMsg;
    itfAlarms : I_AlarmSink;
    // TRUE: an AI decision service answers (bridge); FALSE: the rule decides a part as soon as
    // vision has identified it, without waiting for the deadline and without DecisionFallback
    xDecisionActive : BOOL := TRUE;
END_VAR
VAR_OUTPUT
    stCapture : ST_CaptureMsg;
    udiPlaced : UDINT;
    udiMissed : UDINT;
    udiDropped : UDINT;
    udiVisionMsgs : UDINT;
END_VAR
VAR
    fbQueue : FB_PartQueue;
    fbTrigger : FB_CameraTrigger;
    fbIntake : FB_MessageIntake;
    stRec : ST_PartRecord;
    stNew : ST_PartRecord;
    uiIdx : UINT;
    i : UINT;
END_VAR

// 1. New part at the camera photo-eye.
fbTrigger(xPE1Rising := xPE1Rising, lrBeltPos := lrBeltPos);
stCapture := fbTrigger.stCapture;
IF fbTrigger.xNewPart THEN
    stRec := stNew;
    stRec.udiPartId := fbTrigger.udiNewPartId;
    stRec.lrBeltPosAtCapture := lrBeltPos;
    stRec.lrX := GVL_CellGeometry.PE1_X;         // until vision reports the exact position
    stRec.eState := E_PartState.Captured;
    stRec.tCaptured := TIME();
    IF fbQueue.AddRecord(stRec) = 0 THEN
        RaiseAlarm(E_AlarmId.QueueOverflow);
    ELSIF itfAlarms <> 0 THEN
        itfAlarms.Clear(E_AlarmId.QueueOverflow);
    END_IF
END_IF

// 2. Messages from the bridge (each sequence number once, known part ids only).
fbIntake(stVision := stVision, stDecision := stDecision);
IF fbIntake.xVisionNew THEN
    uiIdx := fbQueue.FindIndex(stVision.udiPartId);
    IF uiIdx > 0 THEN
        stRec := fbQueue.GetRecord(uiIdx);
        IF stRec.eState = E_PartState.Captured THEN
            stRec.xVisionValid := stVision.xValid;
            stRec.usiClass := stVision.usiClass;
            stRec.rConfidence := stVision.rConfidence;
            stRec.lrX := stVision.lrX;
            stRec.lrY := stVision.lrY;
            stRec.lrTheta := stVision.lrTheta;
            stRec.eState := E_PartState.Identified;
            fbQueue.PutRecord(uiIdx, stRec);
            udiVisionMsgs := udiVisionMsgs + 1;
            IF NOT xDecisionActive AND stRec.xVisionValid THEN
                stRec.eDecisionSource := E_DecisionSource.Fallback;
                stRec.eQuality := E_Quality.Unknown;
                Decide(uiIdx, stRec);
            END_IF
        END_IF
    END_IF
END_IF
IF fbIntake.xDecisionNew THEN
    uiIdx := fbQueue.FindIndex(stDecision.udiPartId);
    IF uiIdx > 0 THEN
        stRec := fbQueue.GetRecord(uiIdx);
        IF stRec.eState = E_PartState.Identified THEN
            stRec.eQuality := stDecision.eQuality;
            stRec.rQualityProb := stDecision.rQualityProb;
            stRec.xIdentReliable := stDecision.xIdentReliable;
            stRec.eDecisionSource := E_DecisionSource.Ai;
            Decide(uiIdx, stRec);
        END_IF
    END_IF
END_IF

// 3. Deadline fallback and parts leaving the pick window.
FOR i := 1 TO GVL_Config.MAX_PARTS DO
    stRec := fbQueue.GetRecord(i);
    IF (stRec.eState = E_PartState.Captured OR stRec.eState = E_PartState.Identified)
       AND TIME() - stRec.tCaptured >= GVL_Params.tDecisionDeadline THEN
        stRec.eDecisionSource := E_DecisionSource.Fallback;
        stRec.eQuality := E_Quality.Unknown;
        IF NOT stRec.xVisionValid THEN
            RaiseEventAlarm(E_AlarmId.VisionMissing);
        END_IF
        IF xDecisionActive THEN
            RaiseEventAlarm(E_AlarmId.DecisionFallback);
        END_IF
        Decide(i, stRec);
        stRec := fbQueue.GetRecord(i);
    END_IF
    IF (stRec.eState = E_PartState.Captured OR stRec.eState = E_PartState.Identified
        OR stRec.eState = E_PartState.Decided)
       AND CurrentX(i) > GVL_CellGeometry.PICK_WINDOW_END_X THEN
        SetState(i, E_PartState.Missed);
    END_IF
END_FOR
