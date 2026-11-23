METHOD GetRecord : ST_PartRecord
VAR_INPUT
    uiIdx : UINT;
END_VAR

GetRecord := fbQueue.GetRecord(uiIdx);
