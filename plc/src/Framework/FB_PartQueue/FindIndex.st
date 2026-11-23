// Index of the record with this part id, or 0.
METHOD FindIndex : UINT
VAR_INPUT
    udiPartId : UDINT;
END_VAR
VAR
    i : UINT;
END_VAR

FindIndex := 0;
IF udiPartId = 0 THEN
    RETURN;
END_IF
FOR i := 1 TO GVL_Config.MAX_PARTS DO
    IF aRecords[i].eState <> E_PartState.Free AND aRecords[i].udiPartId = udiPartId THEN
        FindIndex := i;
        RETURN;
    END_IF
END_FOR
