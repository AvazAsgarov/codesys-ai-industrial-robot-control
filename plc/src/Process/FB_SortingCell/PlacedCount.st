// Parts placed in all bins since the last reset of the counters.
METHOD PlacedCount : UINT
VAR
    eBin : E_Bin;
END_VAR

PlacedCount := 0;
FOR eBin := E_Bin.TypeA TO E_Bin.Quarantine DO
    PlacedCount := PlacedCount + aBins[eBin].uiCount;
END_FOR
