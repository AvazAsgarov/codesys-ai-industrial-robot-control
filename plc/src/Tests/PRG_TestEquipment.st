(*
    PRG_TestEquipment
    Purpose : Simulation test harness for the simple equipment FBs (tests/plc/equipment.json).
    Pulses  : write udiPulseMs and set xStartPulse - the harness drives fbPe.xRaw for exactly
              that long in PLC time (tool writes are too slow to time a short pulse).
*)
PROGRAM PRG_TestEquipment
VAR
    fbAlarms : FB_AlarmHandler;
    fbPe : FB_PhotoEye := (tDebounce := T#300MS);
    fbVac : FB_VacuumGripper;
    fbBin : FB_Bin := (eBin := E_Bin.TypeA);
    fbSafety : FB_SafetyMonitor;
    fbAlarmsInitial : FB_AlarmHandler;
    fbPeInitial : FB_PhotoEye := (tDebounce := T#300MS);
    fbVacInitial : FB_VacuumGripper;
    fbBinInitial : FB_Bin := (eBin := E_Bin.TypeA);
    fbSafetyInitial : FB_SafetyMonitor;
    xReinit : BOOL;
    uiPeRises : UINT;
    eVacError : E_AlarmId;
    udiPulseMs : UDINT;
    xStartPulse : BOOL;
    xPulseActive : BOOL;
    tonPulse : TON;
END_VAR

IF xReinit THEN
    xReinit := FALSE;
    fbAlarms := fbAlarmsInitial;
    fbPe := fbPeInitial;
    fbVac := fbVacInitial;
    fbBin := fbBinInitial;
    fbSafety := fbSafetyInitial;
    uiPeRises := 0;
    xPulseActive := FALSE;
END_IF
fbVac.itfAlarms := fbAlarms;
fbSafety.itfAlarms := fbAlarms;

IF xStartPulse THEN
    xStartPulse := FALSE;
    xPulseActive := TRUE;
END_IF
tonPulse(IN := xPulseActive, PT := TO_TIME(udiPulseMs));
IF tonPulse.Q THEN
    xPulseActive := FALSE;
END_IF
fbPe.xRaw := xPulseActive;

fbPe();
IF fbPe.xRising THEN
    uiPeRises := uiPeRises + 1;
END_IF
fbVac();
eVacError := fbVac.ErrorId;
fbBin();
fbSafety();
fbAlarms();
