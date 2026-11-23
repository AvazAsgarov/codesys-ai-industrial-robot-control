// Commands of FB_Robot (start on a rising edge of xExecute).
{attribute 'qualified_only'}
{attribute 'strict'}
TYPE E_RobotCmd :
(
    None := 0,
    MovePtpAcs := 1,       // point-to-point, target in joint space
    MoveLinMcs := 2,       // linear, target in machine coordinates
    MoveLinPcs1 := 3,      // linear, target in PCS_1 (conveyor tracking frame)
    Stop := 4,             // controlled stop, aborts any motion
    Reset := 5             // reset axis group errors
);
END_TYPE
