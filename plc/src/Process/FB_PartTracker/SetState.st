// Updates a part's state. Placed and Dropped parts are counted and their slot is freed.
METHOD SetState
VAR_INPUT
    uiIdx : UINT;
    eState : E_PartState;
END_VAR
VAR
    stR : ST_PartRecord;
END_VAR

stR := fbQueue.GetRecord(uiIdx);
IF stR.eState = E_PartState.Free THEN
    RETURN;
END_IF
CASE eState OF
    E_PartState.Placed:
        udiPlaced := udiPlaced + 1;
        fbQueue.Release(uiIdx);
    E_PartState.Dropped:
        udiDropped := udiDropped + 1;
        fbQueue.Release(uiIdx);
ELSE
    stR.eState := eState;
    fbQueue.PutRecord(uiIdx, stR);
END_CASE
