// Display data for the CODESYS Visualization, prepared by FB_HmiView (no logic in screens).
{attribute 'qualified_only'}
VAR_GLOBAL
    sState : STRING(20);                                   // PackML state
    sMode : STRING(20);                                    // PackML mode
    sPickStep : STRING(20);                                // robot sequence step
    sNewestAlarm : STRING(80);                             // text of the newest alarm
    xExecute : BOOL;                                       // state groups for the machine bar
    xStopped : BOOL;
    xIdle : BOOL;
    xAborted : BOOL;                                       // Aborting or Aborted
    xHeld : BOOL;                                          // Held, Suspended or their acting states
    xActing : BOOL;                                        // Resetting, Starting, Stopping, Clearing
    xManual : BOOL;
    xAnyAlarm : BOOL;                                      // an alarm is active or unacknowledged
    axAlarm : ARRAY[1..16] OF BOOL;                        // per E_AlarmId: active or unacknowledged
    axAlarmActive : ARRAY[1..16] OF BOOL;                  // per E_AlarmId: condition present
    uiPlaced : UINT;                                       // parts placed (all bins)
    xBeltRunning : BOOL;                                   // conveyor faster than BELT_RUNNING_MM_S
    xRobotMoving : BOOL;                                   // a robot motion command is active
    xAnyBinFull : BOOL;                                    // at least one bin reports full
    xJogPermitted : BOOL;                                  // Manual mode and Execute: jog buttons act
END_VAR
