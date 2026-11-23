(*
    PRG_TestTypes
    Purpose : Simulation test harness - exposes configuration values for tests/plc/types.json.
*)
PROGRAM PRG_TestTypes
VAR
    eClassBin0 : E_Bin;
    eFaultClass : E_AlarmClass;
    eWarnClass : E_AlarmClass;
    xLoopback : BOOL;
END_VAR

eClassBin0 := GVL_Params.aClassToBin[0];
eFaultClass := GVL_AlarmDefs.aDefs[E_AlarmId.EStop].eClass;
eWarnClass := GVL_AlarmDefs.aDefs[E_AlarmId.PartMissed].eClass;
xLoopback := GVL_Config.xFeedbackLoopback;
