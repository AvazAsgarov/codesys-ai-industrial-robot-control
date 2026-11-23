// Every alarm of the cell. Definitions (class, text) are in GVL_AlarmDefs.
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_AlarmId :
(
    None := 0,
    EStop := 1,
    DoorOpen := 2,
    BridgeLost := 3,
    AxisGroupError := 4,
    ConveyorError := 5,
    FollowingErrorWarn := 6,
    FollowingErrorFault := 7,
    FeedbackStale := 8,
    VacuumNoGrip := 9,
    VacuumLost := 10,
    PartMissed := 11,
    BinFull := 12,
    VisionMissing := 13,
    DecisionFallback := 14,
    LowConfidence := 15,
    QueueOverflow := 16
);
END_TYPE
