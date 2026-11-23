// Stores the record in a free slot. Returns its index, or 0 when the queue is full.
METHOD AddRecord : UINT
VAR_INPUT
    stRec : ST_PartRecord;
END_VAR
VAR
    i : UINT;
END_VAR

AddRecord := 0;
FOR i := 1 TO GVL_Config.MAX_PARTS DO
    IF aRecords[i].eState = E_PartState.Free THEN
        aRecords[i] := stRec;
        AddRecord := i;
        RETURN;
    END_IF
END_FOR
