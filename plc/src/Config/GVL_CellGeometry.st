// Fixed geometry of the cell. Units: mm and degrees, robot base frame (Z up).
// Kinematics values must match the axis group AxisGroup_Robot (plc/scripts/build_softmotion_base.py).
// Orientations (A, B, C): B = 180 points the tool straight down (verified in simulation).
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

    // Tool pointing straight down
    TOOL_DOWN_A : LREAL := 0;
    TOOL_DOWN_B : LREAL := 180;
    TOOL_DOWN_C : LREAL := 180;

    // Conveyor belt frame: origin at the infeed, +X along the flow direction.
    BELT_ORIGIN : MC_COORD_REF := (X := -1500, Y := -550, Z := 0, A := 0, B := 0, C := 0);
    BELT_SURFACE_Z : LREAL := 0;
    PE1_X : LREAL := 300;                    // camera trigger photo-eye, belt frame [mm]
    PE2_X : LREAL := 1050;                   // pick window start, belt frame [mm]
    PICK_WINDOW_END_X : LREAL := 1750;       // pick window end, belt frame [mm]
    PICK_MARGIN : LREAL := 300;              // do not start a pick this close to the window end [mm]
    // Grip height of each part class above the belt [mm]: the top surface under the suction
    // cup (config/parts.yaml classes, tools/fetch_objects.py meta.json; a unit test keeps
    // both equal)
    PART_HEIGHTS : ARRAY[0..2] OF LREAL := [56.39, 81.19, 83.46];

    // Home position, joint space [deg]
    HOME_ACS : SMC_POS_REF := (a := (a0 := 0, a1 := -30, a2 := 60, a3 := 0, a4 := 60, a5 := 0));
    // Waiting pose above the pick window, tool down (machine coordinates)
    READY_POSE : MC_COORD_REF := (X := -100, Y := -550, Z := 300, A := 0, B := 180, C := 180);
    RETRACT_HEIGHT : LREAL := 100;           // lift above the bin drop pose after release [mm]

    // Drop poses above the bins (tool pointing down), machine coordinates [mm, deg]. Z 300: a
    // held part up to 90 mm tall clears the 160 mm bin rim by 50 mm.
    BIN_DROP : ARRAY[E_Bin.TypeA..E_Bin.Quarantine] OF MC_COORD_REF := [
        (X := -500, Y := 550, Z := 300, A := 0, B := 180, C := 180),
        (X := -300, Y := 550, Z := 300, A := 0, B := 180, C := 180),
        (X := -100, Y := 550, Z := 300, A := 0, B := 180, C := 180),
        (X := 100, Y := 550, Z := 300, A := 0, B := 180, C := 180),
        (X := 300, Y := 550, Z := 300, A := 0, B := 180, C := 180),
        (X := 500, Y := 550, Z := 300, A := 0, B := 180, C := 180)];
END_VAR
