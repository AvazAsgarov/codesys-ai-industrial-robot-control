(*
    PRG_Main
    Purpose : Cell entry point: maps the bridge and HMI variable lists to the sorting cell unit.
    Task    : MainTask, cyclic 4 ms, SoftMotion bus cycle task
    Rule    : thin program - only instantiation, mapping and calls, no logic.
    Commands: GVL_Hmi.eCommand / xAlarmAck are written asynchronously (HMI, OPC UA). They are
              read once per cycle into a snapshot and cleared only if they still hold that
              value, so a command written during the cycle is never lost.
    HMI     : fbHmiPanel turns the visualization's buttons into GVL_Hmi commands before the
              snapshot; fbHmiView prepares GVL_HmiView after the cell has run.
    OPC UA  : published read-only for diagnostics (alarms, pick step) and the HMI.
*)
PROGRAM PRG_Main
{attribute 'symbol' := 'read'}
VAR
    sProjectVersion : STRING := GVL_Constants.PROJECT_VERSION;  // diagnostics: project version visible online and via OPC UA
    fbCell : FB_SortingCell;
    fbHmiPanel : FB_HmiPanel;
    fbHmiView : FB_HmiView;
    eCommand : E_PackMLCommand;
    xAlarmAck : BOOL;
END_VAR

IF NOT GVL_Config.xCellEnabled THEN
    RETURN;
END_IF

fbHmiPanel();
eCommand := GVL_Hmi.eCommand;
xAlarmAck := GVL_Hmi.xAlarmAck;
fbCell(AxisGroup := AxisGroup_Robot,
       ConveyorAxis := Axis_Conveyor,
       eCommand := eCommand,
       eModeRequest := GVL_Hmi.eModeRequest,
       xAlarmAck := xAlarmAck,
       axJogPlus := GVL_Hmi.axJogPlus,
       axJogMinus := GVL_Hmi.axJogMinus,
       rOverride := GVL_Hmi.rOverride,
       xHeartbeat := GVL_Bridge.xHeartbeat,
       aJointPosFb := GVL_Bridge.aJointPosFb,
       aJointTorqueFb := GVL_Bridge.aJointTorqueFb,
       udiFeedbackSeq := GVL_Bridge.udiFeedbackSeq,
       udiFeedbackForSeq := GVL_Bridge.udiFeedbackForSeq,
       xPE1 := GVL_Bridge.xPE1,
       xVacuumOk := GVL_Bridge.xVacuumOk,
       axBinFull := GVL_Bridge.axBinFull,
       xDoorClosed := GVL_Bridge.xDoorClosed,
       xEStopOk := GVL_Bridge.xEStopOk,
       stVision := GVL_Bridge.stVision,
       stDecision := GVL_Bridge.stDecision,
       xDecisionActive := GVL_Bridge.xDecisionActive,
       // joint feedback from the twin once the bridge reports it active (ADR 0008)
       xLoopback := GVL_Config.xFeedbackLoopback AND NOT GVL_Bridge.xTwinActive,
       aJointPosSp => GVL_Bridge.aJointPosSp,
       udiSetpointSeq => GVL_Bridge.udiSetpointSeq,
       lrBeltPos => GVL_Bridge.lrBeltPos,
       lrBeltVel => GVL_Bridge.lrBeltVel,
       xVacuumOn => GVL_Bridge.xVacuumOn,
       stCapture => GVL_Bridge.stCapture,
       eState => GVL_Bridge.eState,
       eMode => GVL_Bridge.eMode,
       ePickStep => GVL_Bridge.ePickStep,
       eNewestAlarm => GVL_Bridge.eNewestAlarm,
       xAlarmError => GVL_Bridge.xAlarmError,
       xAlarmCritical => GVL_Bridge.xAlarmCritical,
       iWorstJoint => GVL_Bridge.iWorstJoint,
       aFollowingError => GVL_Bridge.aFollowingError);
// commands are one-shot: consume the value this cycle has seen, keep a newer one
IF GVL_Hmi.eCommand = eCommand THEN
    GVL_Hmi.eCommand := E_PackMLCommand.None;
END_IF
IF xAlarmAck THEN
    GVL_Hmi.xAlarmAck := FALSE;
END_IF
fbHmiView(Cell := fbCell);
