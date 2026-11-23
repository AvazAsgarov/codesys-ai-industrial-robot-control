// Current belt-frame X of the part in slot uiIdx [mm].
METHOD CurrentX : LREAL
VAR_INPUT
    uiIdx : UINT;
END_VAR
VAR
    stR : ST_PartRecord;
END_VAR

stR := fbQueue.GetRecord(uiIdx);
CurrentX := stR.lrX + (lrBeltPos - stR.lrBeltPosAtCapture);
