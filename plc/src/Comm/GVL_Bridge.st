// Exchange with the Python bridge over OPC UA (published by the symbol configuration).
// Tag names for the bridge: config/opcua_tags.yaml. In Phase 1, tests write the inputs.
{attribute 'qualified_only'}
{attribute 'symbol' := 'readwrite'}
VAR_GLOBAL
    // --- inputs (bridge -> PLC) ---
    xHeartbeat : BOOL;                                     // toggled by the bridge every cycle
    xTwinActive : BOOL;                                    // the twin delivers joint feedback
    aJointPosFb : ARRAY[1..6] OF LREAL;                    // measured joint positions [deg]
    aJointTorqueFb : ARRAY[1..6] OF LREAL;                 // measured joint torques [Nm]
    udiFeedbackSeq : UDINT;                                // increments with every feedback sample
    udiFeedbackForSeq : UDINT;                             // udiSetpointSeq the feedback belongs to
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
    udiSetpointSeq : UDINT;                                // increments with every setpoint sample
    lrBeltPos : LREAL;                                     // conveyor position [mm]
    lrBeltVel : LREAL;                                     // conveyor velocity [mm/s]
    xVacuumOn : BOOL;                                      // vacuum valve
    stCapture : ST_CaptureMsg;
    eState : E_PackMLState;
    eMode : E_PackMLMode;
    // --- diagnostics (PLC -> bridge, HMI) ---
    eNewestAlarm : E_AlarmId;
    xAlarmError : BOOL;                                    // an Error-class alarm is active
    xAlarmCritical : BOOL;                                 // a Critical-class alarm is active
    ePickStep : E_PickStep;
    iWorstJoint : INT;                                     // joint with the largest following error
    aFollowingError : ARRAY[1..6] OF LREAL;                // [deg]
END_VAR
