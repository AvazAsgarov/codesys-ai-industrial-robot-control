// Build/run configuration.
{attribute 'qualified_only'}
VAR_GLOBAL
    // Joint feedback := setpoint (no staleness check) unless the twin reports itself active through
    // GVL_Bridge.xTwinActive. FALSE forces real feedback even without the twin.
    xFeedbackLoopback : BOOL := TRUE;
    // The sorting cell runs in PRG_Main. Simulation tests of single blocks switch it off so their
    // harnesses can own the robot and the conveyor.
    xCellEnabled : BOOL := TRUE;
END_VAR
VAR_GLOBAL CONSTANT
    MAX_PARTS : UINT := 32;                  // capacity of the part queue
END_VAR
