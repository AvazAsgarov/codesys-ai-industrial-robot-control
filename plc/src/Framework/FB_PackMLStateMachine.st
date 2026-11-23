(*
    FB_PackMLStateMachine
    Purpose : PackML unit state machine and mode manager (ISA-TR88.00.02).
    Inputs  : eCommand          - state command; acts once when it changes to a new value
              eModeRequest      - requested mode; accepted only in Stopped, Idle, Aborted
              xStateComplete    - the unit finished the current acting state
              xAbortRequest     - critical condition: abort from any state except Aborting/Aborted
              xStopRequest      - error condition: stop from Idle/Execute/Held/Suspended/acting states
              xSuspendRequest   - starved/blocked: Execute -> Suspending
              xUnsuspendRequest - Suspended -> Unsuspending
    Outputs : eState, eMode, xStateChanged (one cycle), tInState
    States  : the 17 PackML states; acting states leave on xStateComplete
*)
FUNCTION_BLOCK FB_PackMLStateMachine
VAR_INPUT
    eCommand : E_PackMLCommand;
    eModeRequest : E_PackMLMode := E_PackMLMode.Production;
    xStateComplete : BOOL;
    xAbortRequest : BOOL;
    xStopRequest : BOOL;
    xSuspendRequest : BOOL;
    xUnsuspendRequest : BOOL;
END_VAR
VAR_OUTPUT
    eState : E_PackMLState := E_PackMLState.Stopped;
    eMode : E_PackMLMode := E_PackMLMode.Production;
    xStateChanged : BOOL;
    tInState : TIME;
END_VAR
VAR
    eLastCommand : E_PackMLCommand;
    eCmd : E_PackMLCommand;              // command acting in this cycle (None if unchanged)
    eNext : E_PackMLState;
    tEntered : TIME;
END_VAR

// A command acts once, on the cycle it changes to a new value.
IF eCommand <> eLastCommand THEN
    eCmd := eCommand;
ELSE
    eCmd := E_PackMLCommand.None;
END_IF
eLastCommand := eCommand;

eNext := eState;

IF xAbortRequest OR eCmd = E_PackMLCommand.Abort THEN
    IF eState <> E_PackMLState.Aborting AND eState <> E_PackMLState.Aborted THEN
        eNext := E_PackMLState.Aborting;
    END_IF
ELSIF (xStopRequest OR eCmd = E_PackMLCommand.Stop)
      AND eState <> E_PackMLState.Stopped AND eState <> E_PackMLState.Stopping
      AND eState <> E_PackMLState.Aborting AND eState <> E_PackMLState.Aborted
      AND eState <> E_PackMLState.Clearing THEN
    eNext := E_PackMLState.Stopping;
ELSE
    CASE eState OF
        E_PackMLState.Stopped:
            IF eCmd = E_PackMLCommand.Reset THEN eNext := E_PackMLState.Resetting; END_IF
        E_PackMLState.Resetting:
            IF xStateComplete THEN eNext := E_PackMLState.Idle; END_IF
        E_PackMLState.Idle:
            IF eCmd = E_PackMLCommand.Start THEN eNext := E_PackMLState.Starting; END_IF
        E_PackMLState.Starting:
            IF xStateComplete THEN eNext := E_PackMLState.Execute; END_IF
        E_PackMLState.Execute:
            // Producing state: it never ends on xStateComplete, only on commands/requests.
            IF eCmd = E_PackMLCommand.Hold THEN
                eNext := E_PackMLState.Holding;
            ELSIF eCmd = E_PackMLCommand.Suspend OR xSuspendRequest THEN
                eNext := E_PackMLState.Suspending;
            ELSIF eCmd = E_PackMLCommand.Complete THEN
                eNext := E_PackMLState.Completing;
            END_IF
        E_PackMLState.Holding:
            IF xStateComplete THEN eNext := E_PackMLState.Held; END_IF
        E_PackMLState.Held:
            IF eCmd = E_PackMLCommand.Unhold THEN eNext := E_PackMLState.Unholding; END_IF
        E_PackMLState.Unholding:
            IF xStateComplete THEN eNext := E_PackMLState.Execute; END_IF
        E_PackMLState.Suspending:
            IF xStateComplete THEN eNext := E_PackMLState.Suspended; END_IF
        E_PackMLState.Suspended:
            IF eCmd = E_PackMLCommand.Unsuspend OR xUnsuspendRequest THEN
                eNext := E_PackMLState.Unsuspending;
            ELSIF eCmd = E_PackMLCommand.Hold THEN
                eNext := E_PackMLState.Holding;
            END_IF
        E_PackMLState.Unsuspending:
            IF xStateComplete THEN eNext := E_PackMLState.Execute; END_IF
        E_PackMLState.Completing:
            IF xStateComplete THEN eNext := E_PackMLState.Complete; END_IF
        E_PackMLState.Complete:
            IF eCmd = E_PackMLCommand.Reset THEN eNext := E_PackMLState.Resetting; END_IF
        E_PackMLState.Stopping:
            IF xStateComplete THEN eNext := E_PackMLState.Stopped; END_IF
        E_PackMLState.Aborting:
            IF xStateComplete THEN eNext := E_PackMLState.Aborted; END_IF
        E_PackMLState.Aborted:
            IF eCmd = E_PackMLCommand.Clear THEN eNext := E_PackMLState.Clearing; END_IF
        E_PackMLState.Clearing:
            IF xStateComplete THEN eNext := E_PackMLState.Stopped; END_IF
    ELSE
        eNext := E_PackMLState.Stopped;
    END_CASE
END_IF

xStateChanged := eNext <> eState;
IF xStateChanged THEN
    eState := eNext;
    tEntered := TIME();
END_IF
tInState := TIME() - tEntered;

// Mode changes only in a resting state where no motion is commanded.
IF eModeRequest <> eMode AND (eState = E_PackMLState.Stopped OR eState = E_PackMLState.Idle
                              OR eState = E_PackMLState.Aborted) THEN
    eMode := eModeRequest;
END_IF
