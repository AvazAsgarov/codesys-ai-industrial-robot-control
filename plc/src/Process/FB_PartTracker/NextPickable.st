// The decided part furthest downstream inside [lrMinX, lrMaxX] (belt frame), or 0.
METHOD NextPickable : UINT
VAR_INPUT
    lrMinX : LREAL;
    lrMaxX : LREAL;
END_VAR
VAR
    k : UINT;
    lrX : LREAL;
    lrBest : LREAL;
    stR : ST_PartRecord;
END_VAR

NextPickable := 0;
lrBest := lrMinX;
FOR k := 1 TO GVL_Config.MAX_PARTS DO
    stR := fbQueue.GetRecord(k);
    IF stR.eState = E_PartState.Decided THEN
        lrX := CurrentX(k);
        IF lrX >= lrBest AND lrX <= lrMaxX THEN
            lrBest := lrX;
            NextPickable := k;
        END_IF
    END_IF
END_FOR
