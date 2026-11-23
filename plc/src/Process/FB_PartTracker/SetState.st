// Updates a part's state. Placed, Dropped and Missed parts are counted and their slot is freed;
// a missed part raises the PartMissed event.
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
    E_PartState.Missed:
        udiMissed := udiMissed + 1;
        RaiseEventAlarm(E_AlarmId.PartMissed);
        fbQueue.Release(uiIdx);
ELSE
    stR.eState := eState;
    fbQueue.PutRecord(uiIdx, stR);
END_CASE
