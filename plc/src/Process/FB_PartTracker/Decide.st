// Selects the bin, marks the record Decided and stores it.
METHOD PRIVATE Decide
VAR_INPUT
    uiIdx : UINT;
    stRecIn : ST_PartRecord;
END_VAR
VAR
    stOut : ST_PartRecord;
END_VAR

stOut := stRecIn;
stOut.eTargetBin := F_SelectBin(stOut, GVL_Params.rConfidenceThreshold, GVL_Params.aClassToBin);
stOut.eState := E_PartState.Decided;
IF stOut.xVisionValid AND stOut.rConfidence < GVL_Params.rConfidenceThreshold THEN
    RaiseEventAlarm(E_AlarmId.LowConfidence);
END_IF
fbQueue.PutRecord(uiIdx, stOut);
