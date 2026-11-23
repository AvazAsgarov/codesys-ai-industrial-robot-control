(*
    PRG_Tests
    Purpose : Calls every simulation test harness (TEST programs in this folder).
    Task    : TestTask, cyclic 10 ms
*)
PROGRAM PRG_Tests
VAR
END_VAR

PRG_TestMotionSmoke();
PRG_TestTypes();
PRG_TestPackML();
PRG_TestAlarms();
PRG_TestEquipment();
PRG_TestMotion();
PRG_TestJointMonitor();
PRG_TestTracking();
PRG_TestPick();
PRG_TestCell();
