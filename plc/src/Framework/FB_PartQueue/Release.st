METHOD Release
VAR_INPUT
    uiIdx : UINT;
END_VAR

IF uiIdx >= 1 AND uiIdx <= GVL_Config.MAX_PARTS THEN
    aRecords[uiIdx] := stEmpty;
END_IF
