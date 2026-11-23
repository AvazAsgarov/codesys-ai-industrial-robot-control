METHOD GetRecord : ST_PartRecord
VAR_INPUT
    uiIdx : UINT;
END_VAR

IF uiIdx >= 1 AND uiIdx <= GVL_Config.MAX_PARTS THEN
    GetRecord := aRecords[uiIdx];
ELSE
    GetRecord := stEmpty;
END_IF
