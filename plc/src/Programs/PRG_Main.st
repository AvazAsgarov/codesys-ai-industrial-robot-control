(*
    PRG_Main
    Purpose : Cell entry point: maps the bridge and HMI variable lists to the sorting cell unit.
    Task    : MainTask, cyclic 4 ms, SoftMotion bus cycle task
    Rule    : thin program - only instantiation, mapping and calls, no logic.
*)
PROGRAM PRG_Main
VAR
    sProjectVersion : STRING := GVL_Constants.PROJECT_VERSION;  // diagnostics: project version visible online and via OPC UA
    fbCell : FB_SortingCell;
END_VAR

IF NOT GVL_Config.xCellEnabled THEN
    RETURN;
END_IF

fbCell(AxisGroup := AxisGroup_Robot,
       ConveyorAxis := Axis_Conveyor,
       eCommand := GVL_Hmi.eCommand,
       eModeRequest := GVL_Hmi.eModeRequest,
       xAlarmAck := GVL_Hmi.xAlarmAck,
       axJogPlus := GVL_Hmi.axJogPlus,
       axJogMinus := GVL_Hmi.axJogMinus,
       rOverride := GVL_Hmi.rOverride,
       xHeartbeat := GVL_Bridge.xHeartbeat,
       aJointPosFb := GVL_Bridge.aJointPosFb,
       aJointTorqueFb := GVL_Bridge.aJointTorqueFb,
       udiFeedbackSeq := GVL_Bridge.udiFeedbackSeq,
       xPE1 := GVL_Bridge.xPE1,
       xVacuumOk := GVL_Bridge.xVacuumOk,
       axBinFull := GVL_Bridge.axBinFull,
       xDoorClosed := GVL_Bridge.xDoorClosed,
       xEStopOk := GVL_Bridge.xEStopOk,
       stVision := GVL_Bridge.stVision,
       stDecision := GVL_Bridge.stDecision,
       xLoopback := GVL_Config.xFeedbackLoopback,
       aJointPosSp => GVL_Bridge.aJointPosSp,
       lrBeltPos => GVL_Bridge.lrBeltPos,
       lrBeltVel => GVL_Bridge.lrBeltVel,
       xVacuumOn => GVL_Bridge.xVacuumOn,
       stCapture => GVL_Bridge.stCapture,
       eState => GVL_Bridge.eState,
       eMode => GVL_Bridge.eMode);
// commands are one-shot: consumed once the state machine has seen them
GVL_Hmi.eCommand := E_PackMLCommand.None;
GVL_Hmi.xAlarmAck := FALSE;
