(*
    PRG_TestMotionSmoke
    Purpose : Simulation test harness - powers the robot axis group and makes one PTP move.
    Task    : TestTask (via PRG_Tests)
    Spec    : tests/plc/motion_smoke.json
*)
PROGRAM PRG_TestMotionSmoke
VAR
    fbPower : SMC_GroupPower;
    fbEnable : MC_GroupEnable;
    fbMove : MC_MoveDirectAbsolute := (CoordSystem := SMC_COORD_SYSTEM.ACS, VelFactor := 0.5);
    fbReadPos : MC_GroupReadActualPosition := (Enable := TRUE, CoordSystem := SMC_COORD_SYSTEM.ACS);
    xGo : BOOL;
    lrJ1 : LREAL;
    lrJ2 : LREAL;
    xMoveDone : BOOL;
    xMoveError : BOOL;
END_VAR

fbPower(AxisGroup := AxisGroup_Robot, Enable := xGo, bRegulatorOn := TRUE, bDriveStart := TRUE);
fbEnable(AxisGroup := AxisGroup_Robot, Execute := fbPower.Status);
fbMove.Position.a.a0 := 30;
fbMove.Position.a.a1 := -20;
fbMove.Position.a.a2 := 40;
fbMove.Position.a.a3 := 0;
fbMove.Position.a.a4 := 45;
fbMove.Position.a.a5 := 0;
fbMove(AxisGroup := AxisGroup_Robot, Execute := xGo AND fbEnable.Done);
fbReadPos(AxisGroup := AxisGroup_Robot);
lrJ1 := fbReadPos.Position.a.a0;
lrJ2 := fbReadPos.Position.a.a1;
xMoveDone := fbMove.Done;
xMoveError := fbMove.Error;
