// Pose above the tracked part (PCS_1 origin) at height lrZ, tool pointing down.
METHOD PRIVATE TrackedPose : SMC_POS_REF
VAR_INPUT
    lrZ : LREAL;
END_VAR

TrackedPose.c.X := 0;
TrackedPose.c.Y := 0;
TrackedPose.c.Z := lrZ;
TrackedPose.c.A := GVL_CellGeometry.TOOL_DOWN_A;
TrackedPose.c.B := GVL_CellGeometry.TOOL_DOWN_B;
TrackedPose.c.C := GVL_CellGeometry.TOOL_DOWN_C;
