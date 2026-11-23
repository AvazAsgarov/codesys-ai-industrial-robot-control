// Exchange with the Python bridge (OPC UA from Phase 2). In Phase 1, tests write the inputs.
{attribute 'qualified_only'}
VAR_GLOBAL
    // --- inputs (bridge -> PLC) ---
    xHeartbeat : BOOL;                                     // toggled by the bridge every cycle
    aJointPosFb : ARRAY[1..6] OF LREAL;                    // measured joint positions [deg]
    aJointTorqueFb : ARRAY[1..6] OF LREAL;                 // measured joint torques [Nm]
    udiFeedbackSeq : UDINT;                                // increments with every feedback sample
    xPE1 : BOOL;                                           // photo-eye at the camera
    xPE2 : BOOL;                                           // photo-eye at the pick window start
    xVacuumOk : BOOL;                                      // vacuum switch of the suction cup
    axBinFull : ARRAY[E_Bin.TypeA..E_Bin.Quarantine] OF BOOL;
    xDoorClosed : BOOL := TRUE;                            // safety door (TRUE = closed)
    xEStopOk : BOOL := TRUE;                               // emergency stop circuit (TRUE = not pressed)
    stVision : ST_VisionMsg;
    stDecision : ST_DecisionMsg;
    // --- outputs (PLC -> bridge) ---
    aJointPosSp : ARRAY[1..6] OF LREAL;                    // joint setpoints [deg]
    lrBeltPos : LREAL;                                     // conveyor position [mm]
    lrBeltVel : LREAL;                                     // conveyor velocity [mm/s]
    xVacuumOn : BOOL;                                      // vacuum valve
    stCapture : ST_CaptureMsg;
    eState : E_PackMLState;
    eMode : E_PackMLMode;
END_VAR
