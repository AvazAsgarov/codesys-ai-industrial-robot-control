// Steps of FB_PickSequence.
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_PickStep :
(
    Idle := 0,
    MoveHome := 1,
    MoveReady := 2,
    WaitPart := 3,
    StartTracking := 4,
    Approach := 5,
    Descend := 6,
    Grip := 7,
    Lift := 8,
    MoveToBin := 9,
    Release := 10,
    Retract := 11,
    Aborting := 12,
    Aborted := 13,
    Error := 14,
    RecoverLift := 15       // after an abort with a part on the cup: straight up first
);
END_TYPE
