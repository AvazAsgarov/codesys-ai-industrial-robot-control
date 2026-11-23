// Fixed geometry of the cell. Units: mm and degrees, robot base frame (Z up).
// Kinematics values must match the axis group AxisGroup_Robot (plc/scripts/build_softmotion_base.py).
{attribute 'qualified_only'}
VAR_GLOBAL CONSTANT
    // Kin_ArticulatedRobot_6DOF parameters [mm]
    ROBOT_A1 : LREAL := 50;
    ROBOT_D1 : LREAL := 400;
    ROBOT_A2 : LREAL := 450;
    ROBOT_A3 : LREAL := 50;
    ROBOT_D3 : LREAL := 0;
    ROBOT_D4 : LREAL := 450;
    ROBOT_D6 : LREAL := 120;                 // flange + suction tool

    // Conveyor belt frame: origin at the infeed, +X along the flow direction.
    BELT_ORIGIN : MC_COORD_REF := (X := -1500, Y := -550, Z := 0, A := 0, B := 0, C := 0);
    BELT_SURFACE_Z : LREAL := 0;
    PE1_X : LREAL := 300;                    // camera trigger photo-eye, belt frame [mm]
    PE2_X : LREAL := 1050;                   // pick window start, belt frame [mm]
    PICK_WINDOW_END_X : LREAL := 1750;       // pick window end, belt frame [mm]

    // Home position, joint space [deg]
    HOME_ACS : SMC_POS_REF := (a := (a0 := 0, a1 := -30, a2 := 60, a3 := 0, a4 := 60, a5 := 0));

    // Drop poses above the bins (tool pointing down), machine coordinates [mm, deg]
    BIN_DROP : ARRAY[E_Bin.TypeA..E_Bin.Quarantine] OF MC_COORD_REF := [
        (X := -500, Y := 550, Z := 250, A := 0, B := 180, C := 0),
        (X := -300, Y := 550, Z := 250, A := 0, B := 180, C := 0),
        (X := -100, Y := 550, Z := 250, A := 0, B := 180, C := 0),
        (X := 100, Y := 550, Z := 250, A := 0, B := 180, C := 0),
        (X := 300, Y := 550, Z := 250, A := 0, B := 180, C := 0),
        (X := 500, Y := 550, Z := 250, A := 0, B := 180, C := 0)];
END_VAR
