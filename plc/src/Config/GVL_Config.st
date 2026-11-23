// Build/run configuration.
{attribute 'qualified_only'}
VAR_GLOBAL
    // TRUE until the digital twin is connected (Phase 2): joint feedback := setpoint, no staleness check.
    xFeedbackLoopback : BOOL := TRUE;
    // The sorting cell runs in PRG_Main. Simulation tests of single blocks switch it off so their
    // harnesses can own the robot and the conveyor.
    xCellEnabled : BOOL := TRUE;
END_VAR
VAR_GLOBAL CONSTANT
    MAX_PARTS : UINT := 32;                  // capacity of the part queue
END_VAR
