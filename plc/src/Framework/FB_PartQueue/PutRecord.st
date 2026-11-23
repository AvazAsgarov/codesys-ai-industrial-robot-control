METHOD PutRecord
VAR_INPUT
    uiIdx : UINT;
    stRec : ST_PartRecord;
END_VAR

IF uiIdx >= 1 AND uiIdx <= GVL_Config.MAX_PARTS THEN
    aRecords[uiIdx] := stRec;
END_IF
