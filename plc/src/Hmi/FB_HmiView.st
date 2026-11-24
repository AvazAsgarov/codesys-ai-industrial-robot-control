(*
    FB_HmiView
    Purpose : Prepares the display data of the visualization (GVL_HmiView): state and mode texts,
              state groups for the machine bar, alarm rows (active or unacknowledged, and the
              condition itself), newest alarm text, equipment signals and the placed counter.
    In/Out  : Cell - the sorting cell (read only)
    Outputs : GVL_HmiView
*)
FUNCTION_BLOCK FB_HmiView
VAR_IN_OUT
    Cell : FB_SortingCell;
END_VAR
VAR
    i : INT;
    stAlarm : ST_Alarm;
END_VAR
VAR CONSTANT
    BELT_RUNNING_MM_S : LREAL := 1.0;  // the belt counts as running above this speed
    // HMI row i shows alarm ALARM_ROWS[i] (E_AlarmId is strict: no integer arithmetic on it)
    ALARM_ROWS : ARRAY[1..16] OF E_AlarmId := [
        E_AlarmId.EStop, E_AlarmId.DoorOpen, E_AlarmId.BridgeLost, E_AlarmId.AxisGroupError,
        E_AlarmId.ConveyorError, E_AlarmId.FollowingErrorWarn, E_AlarmId.FollowingErrorFault,
        E_AlarmId.FeedbackStale, E_AlarmId.VacuumNoGrip, E_AlarmId.VacuumLost,
        E_AlarmId.PartMissed, E_AlarmId.BinFull, E_AlarmId.VisionMissing,
        E_AlarmId.DecisionFallback, E_AlarmId.LowConfidence, E_AlarmId.QueueOverflow];
END_VAR

CASE Cell.eState OF
    E_PackMLState.Clearing: GVL_HmiView.sState := 'Clearing';
    E_PackMLState.Stopped: GVL_HmiView.sState := 'Stopped';
    E_PackMLState.Starting: GVL_HmiView.sState := 'Starting';
    E_PackMLState.Idle: GVL_HmiView.sState := 'Idle';
    E_PackMLState.Suspended: GVL_HmiView.sState := 'Suspended';
    E_PackMLState.Execute: GVL_HmiView.sState := 'Execute';
    E_PackMLState.Stopping: GVL_HmiView.sState := 'Stopping';
    E_PackMLState.Aborting: GVL_HmiView.sState := 'Aborting';
    E_PackMLState.Aborted: GVL_HmiView.sState := 'Aborted';
    E_PackMLState.Holding: GVL_HmiView.sState := 'Holding';
    E_PackMLState.Held: GVL_HmiView.sState := 'Held';
    E_PackMLState.Unholding: GVL_HmiView.sState := 'Unholding';
    E_PackMLState.Suspending: GVL_HmiView.sState := 'Suspending';
    E_PackMLState.Unsuspending: GVL_HmiView.sState := 'Unsuspending';
    E_PackMLState.Resetting: GVL_HmiView.sState := 'Resetting';
    E_PackMLState.Completing: GVL_HmiView.sState := 'Completing';
    E_PackMLState.Complete: GVL_HmiView.sState := 'Complete';
ELSE
    GVL_HmiView.sState := 'Undefined';
END_CASE
CASE Cell.eMode OF
    E_PackMLMode.Production: GVL_HmiView.sMode := 'Production';
    E_PackMLMode.Maintenance: GVL_HmiView.sMode := 'Maintenance';
    E_PackMLMode.Manual: GVL_HmiView.sMode := 'Manual';
END_CASE
CASE Cell.ePickStep OF
    E_PickStep.Idle: GVL_HmiView.sPickStep := 'Idle';
    E_PickStep.MoveHome: GVL_HmiView.sPickStep := 'Moving home';
    E_PickStep.MoveReady: GVL_HmiView.sPickStep := 'Moving to ready';
    E_PickStep.WaitPart: GVL_HmiView.sPickStep := 'Waiting for a part';
    E_PickStep.StartTracking: GVL_HmiView.sPickStep := 'Tracking the belt';
    E_PickStep.Approach: GVL_HmiView.sPickStep := 'Approaching';
    E_PickStep.Descend: GVL_HmiView.sPickStep := 'Descending';
    E_PickStep.Grip: GVL_HmiView.sPickStep := 'Gripping';
    E_PickStep.Lift: GVL_HmiView.sPickStep := 'Lifting';
    E_PickStep.MoveToBin: GVL_HmiView.sPickStep := 'Moving to bin';
    E_PickStep.Release: GVL_HmiView.sPickStep := 'Releasing';
    E_PickStep.Retract: GVL_HmiView.sPickStep := 'Retracting';
    E_PickStep.Aborting: GVL_HmiView.sPickStep := 'Stopping';
    E_PickStep.Aborted: GVL_HmiView.sPickStep := 'Stopped (abort)';
    E_PickStep.Error: GVL_HmiView.sPickStep := 'Error';
    E_PickStep.RecoverLift: GVL_HmiView.sPickStep := 'Recovering';
END_CASE

GVL_HmiView.xExecute := Cell.eState = E_PackMLState.Execute;
GVL_HmiView.xStopped := Cell.eState = E_PackMLState.Stopped;
GVL_HmiView.xIdle := Cell.eState = E_PackMLState.Idle;
GVL_HmiView.xAborted := Cell.eState = E_PackMLState.Aborted OR Cell.eState = E_PackMLState.Aborting;
GVL_HmiView.xHeld := Cell.eState = E_PackMLState.Held OR Cell.eState = E_PackMLState.Suspended
                     OR Cell.eState = E_PackMLState.Holding OR Cell.eState = E_PackMLState.Suspending;
GVL_HmiView.xActing := Cell.eState = E_PackMLState.Resetting OR Cell.eState = E_PackMLState.Starting
                       OR Cell.eState = E_PackMLState.Stopping OR Cell.eState = E_PackMLState.Clearing
                       OR Cell.eState = E_PackMLState.Unholding OR Cell.eState = E_PackMLState.Unsuspending;
GVL_HmiView.xManual := Cell.eMode = E_PackMLMode.Manual;
GVL_HmiView.xJogPermitted := GVL_HmiView.xManual AND GVL_HmiView.xExecute;

GVL_HmiView.xAnyAlarm := FALSE;
FOR i := 1 TO 16 DO
    stAlarm := Cell.AlarmState(ALARM_ROWS[i]);
    GVL_HmiView.axAlarmActive[i] := stAlarm.xActive;
    GVL_HmiView.axAlarm[i] := stAlarm.xActive OR NOT stAlarm.xAcked;
    GVL_HmiView.xAnyAlarm := GVL_HmiView.xAnyAlarm OR GVL_HmiView.axAlarm[i];
END_FOR
GVL_HmiView.sNewestAlarm := GVL_AlarmDefs.aDefs[Cell.eNewestAlarm].sText;
GVL_HmiView.uiPlaced := Cell.PlacedCount();
GVL_HmiView.xBeltRunning := ABS(Cell.lrBeltVel) > BELT_RUNNING_MM_S;
GVL_HmiView.xRobotMoving := Cell.RobotMoving();
GVL_HmiView.xAnyBinFull := Cell.AnyBinFull();
