VAR
    i : UINT;
END_VAR

Count := 0;
FOR i := 1 TO GVL_Config.MAX_PARTS DO
    IF aRecords[i].eState <> E_PartState.Free THEN
        Count := Count + 1;
    END_IF
END_FOR
